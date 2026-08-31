"""Durability's second checkpoint: `invocation_state` itself.

`Graph.serialize_state()` (Strands 1.53.0) persists topology only --
completed/failed/interrupted nodes, each node's bare `MultiAgentResult`, the
next nodes to run, and interrupt state. It never includes `invocation_state`,
and every node in this codebase (`AgentTurnNode`, `ModeratorHub`,
`ModeratorDecision`) writes its output only into `invocation_state`, not into
a node result -- so Strands' own `FileSessionManager` checkpoint alone is not
enough to resume with the debate's actual content intact (design.md,
Decision 1). `InvocationStatePersistenceHook` fills that gap with a sibling
file inside the same `FileSessionManager` session directory, kept in sync on
the same events Strands' own session manager already listens to.
"""

import glob
import json
import os
import tempfile
from typing import Any

from strands.hooks import AfterMultiAgentInvocationEvent, AfterNodeCallEvent, HookProvider, HookRegistry

from src.core import config

# Mirrors `FileSessionManager.SESSION_PREFIX` (strands/session/file_session_manager.py),
# which is not part of that class's public interface -- there is no accessor for
# "the directory a given session_id lives in" that doesn't also create the session
# as a side effect (`RepositorySessionManager.__init__` auto-creates on a cache miss),
# which would defeat a plain existence check for an unknown run_id.
SESSION_DIR_PREFIX = "session_"
INVOCATION_STATE_FILENAME = "invocation_state.json"

# Mirrors `strands.session.s3_session_manager`'s own private module-level
# constants (`SESSION_PREFIX`, `MULTI_AGENT_PREFIX`) and `Graph`'s private
# `_DEFAULT_GRAPH_ID` -- same reason as `SESSION_DIR_PREFIX` above: no public
# accessor exists for "the S3 key this session/graph lives under" that
# doesn't also create it. `build_graph()` never passes a custom `id=` to
# `GraphBuilder`, so every graph checkpoint in this codebase lives under
# `_DEFAULT_GRAPH_ID` (confirmed against installed strands 1.53.0).
S3_SESSION_KEY_PREFIX = "session_"
S3_MULTI_AGENT_KEY_PREFIX = "multi_agent_"
S3_DEFAULT_GRAPH_ID = "default_graph"


def _use_s3() -> bool:
    """When true, every function below ignores its `storage_dir` argument and
    reads/writes S3 instead -- the AWS deployment target (deploy-to-agentcore
    design.md, Decision 4). `storage_dir` stays a required parameter either
    way so every call site is identical regardless of target."""
    return bool(config.S3_SESSION_BUCKET)


def _s3_client():
    import boto3

    return boto3.client("s3", region_name=config.AWS_REGION)


def _s3_session_prefix(run_id: str) -> str:
    prefix = (config.S3_SESSION_PREFIX or "").strip("/")
    base = f"{S3_SESSION_KEY_PREFIX}{run_id}/"
    return f"{prefix}/{base}" if prefix else base


def _s3_invocation_state_key(run_id: str) -> str:
    return _s3_session_prefix(run_id) + INVOCATION_STATE_FILENAME


def _s3_multi_agent_key(run_id: str) -> str:
    return f"{_s3_session_prefix(run_id)}multi_agents/{S3_MULTI_AGENT_KEY_PREFIX}{S3_DEFAULT_GRAPH_ID}/multi_agent.json"


def _s3_get_object(key: str) -> bytes | None:
    from botocore.exceptions import ClientError

    try:
        response = _s3_client().get_object(Bucket=config.S3_SESSION_BUCKET, Key=key)
        return response["Body"].read()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise


def _s3_object_exists(key: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        _s3_client().head_object(Bucket=config.S3_SESSION_BUCKET, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return False
        raise


def _session_dir(storage_dir: str, run_id: str) -> str:
    return os.path.join(storage_dir, f"{SESSION_DIR_PREFIX}{run_id}")


def session_exists(storage_dir: str, run_id: str) -> bool:
    if _use_s3():
        return _s3_object_exists(_s3_invocation_state_key(run_id))
    return os.path.isdir(_session_dir(storage_dir, run_id))


def _invocation_state_path(storage_dir: str, run_id: str) -> str:
    return os.path.join(_session_dir(storage_dir, run_id), INVOCATION_STATE_FILENAME)


def save_invocation_state(storage_dir: str, run_id: str, invocation_state: dict[str, Any]) -> None:
    """Atomically write `invocation_state` for `run_id`, creating its session directory if needed."""
    if _use_s3():
        _s3_client().put_object(
            Bucket=config.S3_SESSION_BUCKET,
            Key=_s3_invocation_state_key(run_id),
            Body=json.dumps(invocation_state, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return

    session_dir = _session_dir(storage_dir, run_id)
    os.makedirs(session_dir, mode=0o700, exist_ok=True)

    path = _invocation_state_path(storage_dir, run_id)
    fd, tmp_path = tempfile.mkstemp(dir=session_dir, prefix=".invocation_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(invocation_state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_invocation_state(storage_dir: str, run_id: str) -> dict[str, Any] | None:
    if _use_s3():
        body = _s3_get_object(_s3_invocation_state_key(run_id))
        return json.loads(body) if body is not None else None

    path = _invocation_state_path(storage_dir, run_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class PersistedGraphStatus:
    """What `resume()` needs to know from Strands' own checkpoint, read directly
    from disk -- deliberately without constructing a `Graph`/`FileSessionManager`
    first. `Graph.deserialize_state()` resets to a brand-new `GraphState` (status
    back to PENDING) whenever the persisted `next_nodes_to_execute` is empty --
    true for both a run that never started and one that already completed --
    so the application must decide from the raw payload whether there is
    genuinely resumable work *before* rebuilding the graph, rather than trust
    whatever state the rebuilt graph happens to expose afterward."""

    def __init__(self, status: str, has_next_nodes: bool, pending_interrupt_id: str | None) -> None:
        self.status = status
        self.has_next_nodes = has_next_nodes
        self.pending_interrupt_id = pending_interrupt_id


def read_persisted_graph_status(storage_dir: str, run_id: str) -> PersistedGraphStatus | None:
    """Reads the one `multi_agent.json` checkpoint for `run_id`'s session, or
    None if the session exists but no graph checkpoint has been written yet
    (killed before the first `MultiAgentInitializedEvent`/`AfterNodeCallEvent`)."""
    if _use_s3():
        body = _s3_get_object(_s3_multi_agent_key(run_id))
        if body is None:
            return None
        payload = json.loads(body)
    else:
        pattern = os.path.join(_session_dir(storage_dir, run_id), "multi_agents", "*", "multi_agent.json")
        matches = glob.glob(pattern)
        if not matches:
            return None

        with open(matches[0], encoding="utf-8") as f:
            payload = json.load(f)

    interrupts = payload.get("_internal_state", {}).get("interrupt_state", {}).get("interrupts", {})
    pending_interrupt_id = next(
        (interrupt_id for interrupt_id, interrupt in interrupts.items() if interrupt.get("response") is None),
        None,
    )

    return PersistedGraphStatus(
        status=payload["status"],
        has_next_nodes=bool(payload.get("next_nodes_to_execute")),
        pending_interrupt_id=pending_interrupt_id,
    )


class InvocationStatePersistenceHook(HookProvider):
    """Keeps `invocation_state.json` in sync with the live `invocation_state`
    dict, on the same events `SessionManager` itself uses for its own
    `sync_multi_agent` (strands/session/session_manager.py)."""

    def __init__(self, storage_dir: str, run_id: str) -> None:
        self._storage_dir = storage_dir
        self._run_id = run_id

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterNodeCallEvent, self._persist)
        registry.add_callback(AfterMultiAgentInvocationEvent, self._persist)

    def _persist(self, event: AfterNodeCallEvent | AfterMultiAgentInvocationEvent) -> None:
        if event.invocation_state is None:
            return
        save_invocation_state(self._storage_dir, self._run_id, event.invocation_state)

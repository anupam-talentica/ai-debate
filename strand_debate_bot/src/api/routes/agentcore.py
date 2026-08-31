"""AgentCore Runtime's required invocation contract (`POST /invocations`,
`GET /ping`), sitting alongside -- not replacing -- `debates.py`'s existing
REST surface (deploy-to-agentcore design.md, Decision 1). This module holds
no debate logic of its own: it only translates a dispatched payload into the
same `DebateService` calls the REST routes already make, and formats the
result back.

Session identity: AgentCore's `runtimeSessionId`, carried on every request
via the `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` header (AWS's
documented HTTP-protocol session header), is used directly as this debate's
`run_id` -- one debate maps 1:1 to one AgentCore session (design.md,
Decision 2), so a pause-then-resume flow relies on AgentCore's own
session-to-microVM affinity rather than a second identifier space.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.services.debate_service import DebateService
from src.api.services.exceptions import DebateAwaitingInputError, DebateExecutionError, DebateTimeoutError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AgentCore"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_SESSION_ID_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"

_KNOWN_ACTIONS = {"start", "stream", "submit_audience_question", "resume", "invoke"}


def _service(request: Request) -> DebateService:
    return request.app.state.debate_service


@router.get("/ping")
async def ping() -> dict[str, str]:
    """Liveness check independent of any run's state (specs/agentcore-deployment,
    "Liveness check independent of any debate run") -- unlike `/debate/health`,
    this never touches `DebateService` at all."""
    return {"status": "healthy"}


@router.post("/invocations")
async def invocations(req: Request) -> Any:
    """Single dispatched endpoint (specs/agentcore-deployment, "Single
    dispatched invocation endpoint"): reads `action` from the payload and
    calls the matching `DebateService` method, using the AgentCore session
    header as that debate's `run_id` throughout.

    Parses the body directly rather than declaring a `dict[str, Any]`
    parameter -- AgentCore's `InvokeAgentRuntime` doesn't necessarily send
    `Content-Type: application/json` the way a browser/httpx client would,
    and FastAPI's automatic body-model inference 422s on that mismatch."""
    body = await req.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Request body is not valid JSON: {exc}") from exc

    runtime_session_id = req.headers.get(_SESSION_ID_HEADER)

    action = payload.get("action")
    if action not in _KNOWN_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized action {action!r}; expected one of {sorted(_KNOWN_ACTIONS)}",
        )
    if not runtime_session_id:
        raise HTTPException(status_code=400, detail=f"Missing required {_SESSION_ID_HEADER} header")

    service = _service(req)
    run_id = runtime_session_id

    if action == "start":
        topic = payload.get("topic", "")
        if not topic.strip():
            raise HTTPException(status_code=400, detail="Topic cannot be empty")
        started_run_id = service.start(topic, audience_question=payload.get("audience_question"), run_id=run_id)
        logger.info("AgentCore start [%s]: %s...", started_run_id, topic[:50])
        return {"run_id": started_run_id}

    if action == "stream":
        generator = service.stream_registered(run_id)
        if generator is None:
            raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")
        return StreamingResponse(generator, media_type="text/event-stream", headers=_SSE_HEADERS)

    if action == "submit_audience_question":
        question = payload.get("question", "")
        if not question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        outcome = service.submit_audience_question(run_id, question)
        if outcome is None:
            raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")
        if outcome == "not_waiting":
            raise HTTPException(status_code=409, detail=f"Run {run_id} is not awaiting an audience question")
        return {"run_id": run_id, "status": "resuming"}

    if action == "resume":
        resumed_run_id = service.resume(run_id)
        if resumed_run_id is None:
            raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")
        return {"run_id": resumed_run_id}

    # action == "invoke"
    topic = payload.get("topic", "")
    if not topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    try:
        result = await service.invoke(topic, audience_question=payload.get("audience_question"), run_id=run_id)
        return result
    except DebateTimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except DebateAwaitingInputError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "run_id": exc.run_id}) from exc
    except DebateExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

import json
import tempfile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes.debates import router as debate_router
from src.api.services.debate_service import DebateService
from src.api.services.run_registry import RunRegistry
from src.core.graph import build_graph
from src.core.state import build_invocation_state
from tests.fakes import FakeMemoryStore, FakeModel


def make_app(
    model: FakeModel | None = None, timeout_seconds: float = 5.0, session_storage_dir: str | None = None
) -> FastAPI:
    model = model or FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    # A fresh tmp dir per call by default, so unrelated tests never share
    # on-disk session state -- only tests that explicitly simulate a restart
    # pass the same session_storage_dir to two separate make_app() calls.
    session_storage_dir = session_storage_dir or tempfile.mkdtemp(prefix="debate_test_session_")

    def graph_factory(run_id: str):
        return build_graph(model=model, memory_store=FakeMemoryStore(), run_id=run_id, session_storage_dir=session_storage_dir)

    app = FastAPI()
    app.state.debate_service = DebateService(
        graph_factory, RunRegistry(), session_storage_dir, timeout_seconds=timeout_seconds
    )
    app.include_router(debate_router)
    return app


def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def read_sse(response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
async def test_health():
    async with client_for(make_app()) as client:
        response = await client.get("/debate/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_invoke_with_pre_supplied_question_completes():
    """spec: "A pre-supplied question lets the debate complete in one call" """
    async with client_for(make_app()) as client:
        response = await client.post(
            "/debate/invoke",
            json={"topic": "Remote work beats office work", "audience_question": "What about culture?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["winner"] == "Pro"
    assert body["justification"] == "j"
    assert body["audience_question"] == "What about culture?"
    assert body["pro_audience_answer"] and body["con_audience_answer"]


@pytest.mark.asyncio
async def test_invoke_without_question_returns_409_with_run_id():
    """spec: "No pre-supplied question surfaces the pause as an explicit error" """
    async with client_for(make_app()) as client:
        response = await client.post("/debate/invoke", json={"topic": "Remote work beats office work"})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["run_id"]


@pytest.mark.asyncio
async def test_invoke_timeout_returns_408():
    """spec: "Execution exceeding the timeout fails distinctly" -- a timeout of
    0 forces asyncio.wait_for to expire before the graph can complete even a
    single node."""
    async with client_for(make_app(timeout_seconds=0)) as client:
        response = await client.post("/debate/invoke", json={"topic": "Remote work beats office work"})

    assert response.status_code == 408


@pytest.mark.asyncio
async def test_stream_fresh_reaches_pause_then_reports_it():
    """spec: "A fresh run streams events up to the pause, then reports it explicitly" -
    GET /debate/stream has no audience_question field, so every run reaches the
    pause; it can never stream to completion (spec correction made during 8.3)."""
    async with client_for(make_app()) as client:
        async with client.stream("GET", "/debate/stream", params={"topic": "Remote work"}) as response:
            assert response.status_code == 200
            events = await read_sse(response)

    node_names = [e["node"] for e in events]
    assert node_names[0] == "RUN_START"
    assert node_names[-1] == "AWAITING_AUDIENCE_QUESTION_UNSUPPORTED"
    assert "con_rebuttal" in node_names  # reached through the rebuttal round


@pytest.mark.asyncio
async def test_start_stream_and_submit_audience_question_round_trip():
    """spec: "Submitting a question resumes a paused run to completion" """
    app = make_app()
    async with client_for(app) as client:
        start_response = await client.post("/debate/start", json={"topic": "Remote work beats office work"})
        run_id = start_response.json()["run_id"]

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            assert response.status_code == 200
            events = await read_sse(response)
        assert events[-1]["node"] == "AWAITING_AUDIENCE_QUESTION"

        submit_response = await client.post(
            f"/debate/{run_id}/audience-question", json={"question": "What about accessibility?"}
        )
        assert submit_response.status_code == 200
        assert submit_response.json() == {"run_id": run_id, "status": "resuming"}

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            assert response.status_code == 200
            resume_events = await read_sse(response)

    assert resume_events[-1]["node"] == "COMPLETE"
    assert resume_events[-1]["state"]["winner"] == "Pro"
    assert resume_events[-1]["state"]["audience_question"] == "What about accessibility?"


@pytest.mark.asyncio
async def test_submit_audience_question_unknown_run_id_returns_404():
    async with client_for(make_app()) as client:
        response = await client.post("/debate/unknown-run/audience-question", json={"question": "q?"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_submit_audience_question_when_not_waiting_returns_409():
    app = make_app()
    async with client_for(app) as client:
        start_response = await client.post(
            "/debate/start",
            json={"topic": "Remote work beats office work", "audience_question": "Pre-supplied?"},
        )
        run_id = start_response.json()["run_id"]

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            await read_sse(response)  # drain to completion; never pauses since pre-supplied

        response = await client.post(f"/debate/{run_id}/audience-question", json={"question": "too late?"})

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_runs_are_isolated():
    """spec: "Concurrent runs are isolated" """
    app = make_app()
    async with client_for(app) as client:
        start_a = await client.post("/debate/start", json={"topic": "Topic A", "audience_question": "qa?"})
        start_b = await client.post("/debate/start", json={"topic": "Topic B", "audience_question": "qb?"})
        run_a, run_b = start_a.json()["run_id"], start_b.json()["run_id"]

        async with client.stream("GET", f"/debate/stream/{run_a}") as response:
            events_a = await read_sse(response)
        async with client.stream("GET", f"/debate/stream/{run_b}") as response:
            events_b = await read_sse(response)

    assert events_a[-1]["state"]["topic"] == "Topic A"
    assert events_b[-1]["state"]["topic"] == "Topic B"
    assert events_a[-1]["run_id"] == run_a
    assert events_b[-1]["run_id"] == run_b


@pytest.mark.asyncio
async def test_stream_unknown_run_id_returns_404():
    async with client_for(make_app()) as client:
        response = await client.get("/debate/stream/unknown-run")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resume_unknown_run_id_returns_404():
    """spec: "Resuming an unknown run identifier fails" """
    async with client_for(make_app()) as client:
        response = await client.get("/debate/resume/some-run-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resume_of_a_run_killed_mid_execution_continues_to_completion():
    """spec: "Resuming an interrupted run continues it toward completion".
    FakeModel has no real latency, so a background task driving it runs to
    completion (or the pause) far faster than a test could race a cancellation
    against it over real HTTP. Instead, the pre-restart state is produced the
    same deterministic way test_durability.py does -- driving a directly-built
    graph and breaking out of its stream partway -- which leaves exactly the
    on-disk checkpoint a real kill at that point would; only the resume half
    goes through the actual API surface this test is about."""
    session_storage_dir = tempfile.mkdtemp(prefix="debate_test_session_")
    run_id = "killed-mid-flight"
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})

    graph = build_graph(model=model, memory_store=FakeMemoryStore(), run_id=run_id, session_storage_dir=session_storage_dir)
    state = build_invocation_state("Remote work beats office work")
    async for event in graph.stream_async("run", invocation_state=state):
        if event.get("type") == "multiagent_node_stop" and event.get("node_id") == "con_opening":
            break

    app2 = make_app(model=model, session_storage_dir=session_storage_dir)
    async with client_for(app2) as client:
        resume_response = await client.get(f"/debate/resume/{run_id}")
        assert resume_response.status_code == 200
        assert resume_response.json() == {"run_id": run_id}

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            events = await read_sse(response)

    assert events[-1]["node"] == "AWAITING_AUDIENCE_QUESTION"  # no pre-supplied question -- pauses as usual


@pytest.mark.asyncio
async def test_resume_of_a_paused_run_leaves_it_paused():
    """spec: "Resuming a paused run leaves it paused" """
    session_storage_dir = tempfile.mkdtemp(prefix="debate_test_session_")
    app1 = make_app(session_storage_dir=session_storage_dir)

    async with client_for(app1) as client:
        start_response = await client.post("/debate/start", json={"topic": "Remote work beats office work"})
        run_id = start_response.json()["run_id"]
        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            events = await read_sse(response)
        assert events[-1]["node"] == "AWAITING_AUDIENCE_QUESTION"

    # A second app/service/registry -- as if the process restarted -- shares
    # only the on-disk session_storage_dir, not app1's in-memory RunRegistry.
    app2 = make_app(session_storage_dir=session_storage_dir)
    async with client_for(app2) as client:
        resume_response = await client.get(f"/debate/resume/{run_id}")
        assert resume_response.status_code == 200

        submit_response = await client.post(
            f"/debate/{run_id}/audience-question", json={"question": "What about accessibility?"}
        )
        assert submit_response.status_code == 200

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            events = await read_sse(response)

    assert events[-1]["node"] == "COMPLETE"
    assert events[-1]["state"]["winner"] == "Pro"
    assert events[-1]["state"]["audience_question"] == "What about accessibility?"


@pytest.mark.asyncio
async def test_stream_right_after_resuming_a_paused_run_does_not_hang():
    """Regression test: resume()'s paused branch registers a fresh, empty
    event_queue and starts no _drive task -- without explicitly pushing the
    pause event onto it, a client streaming before the question is ever
    submitted would wait forever for a sentinel nothing would produce."""
    session_storage_dir = tempfile.mkdtemp(prefix="debate_test_session_")
    app1 = make_app(session_storage_dir=session_storage_dir)
    async with client_for(app1) as client:
        start_response = await client.post("/debate/start", json={"topic": "Remote work beats office work"})
        run_id = start_response.json()["run_id"]
        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            await read_sse(response)

    app2 = make_app(session_storage_dir=session_storage_dir)
    async with client_for(app2) as client:
        resume_response = await client.get(f"/debate/resume/{run_id}")
        assert resume_response.status_code == 200

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            events = await read_sse(response)

    assert events == [{"node": "AWAITING_AUDIENCE_QUESTION", "run_id": run_id}]


@pytest.mark.asyncio
async def test_resume_of_an_already_completed_run_does_not_rerun():
    """Regression test: resume()'s terminal branch must key off the persisted
    `status` field, not off whether next_nodes_to_execute reads empty -- that
    reads empty at every round boundary too (design.md addendum), not only
    once a run has genuinely completed."""
    session_storage_dir = tempfile.mkdtemp(prefix="debate_test_session_")
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    app1 = make_app(model=model, session_storage_dir=session_storage_dir)

    async with client_for(app1) as client:
        start_response = await client.post(
            "/debate/start",
            json={"topic": "Remote work beats office work", "audience_question": "Pre-supplied?"},
        )
        run_id = start_response.json()["run_id"]
        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            events = await read_sse(response)
        assert events[-1]["node"] == "COMPLETE"

    calls_before_resume = len(model.calls)
    app2 = make_app(model=model, session_storage_dir=session_storage_dir)
    async with client_for(app2) as client:
        resume_response = await client.get(f"/debate/resume/{run_id}")
        assert resume_response.status_code == 200

        async with client.stream("GET", f"/debate/stream/{run_id}") as response:
            events = await read_sse(response)

    assert events == [{"node": "COMPLETE", "run_id": run_id, "state": events[0]["state"]}]
    assert events[0]["state"]["winner"] == "Pro"
    assert len(model.calls) == calls_before_resume  # nothing re-ran

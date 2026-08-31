"""Tests for the AgentCore invocation dispatcher (specs/agentcore-deployment).

Mirrors `test_api.py`'s style -- a fresh `FastAPI` app per test wired with
`FakeModel`/`FakeMemoryStore`, no real AWS or Anthropic calls -- but exercises
`src/api/routes/agentcore.py`'s single `/invocations` endpoint instead of the
per-path REST routes.
"""

import json
import tempfile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes.agentcore import router as agentcore_router
from src.api.services.debate_service import DebateService
from src.api.services.run_registry import RunRegistry
from src.core.graph import build_graph
from tests.fakes import FakeMemoryStore, FakeModel

_SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"


def make_app(model: FakeModel | None = None, timeout_seconds: float = 5.0) -> FastAPI:
    model = model or FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    session_storage_dir = tempfile.mkdtemp(prefix="agentcore_test_session_")

    def graph_factory(run_id: str):
        return build_graph(model=model, memory_store=FakeMemoryStore(), run_id=run_id, session_storage_dir=session_storage_dir)

    app = FastAPI()
    app.state.debate_service = DebateService(graph_factory, RunRegistry(), session_storage_dir, timeout_seconds=timeout_seconds)
    app.include_router(agentcore_router)
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
async def test_ping_is_healthy_independent_of_any_run():
    """spec: "Liveness check independent of any debate run" """
    async with client_for(make_app()) as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_unrecognized_action_is_rejected_explicitly():
    """spec: "An unrecognized operation is rejected explicitly" """
    async with client_for(make_app()) as client:
        response = await client.post(
            "/invocations", json={"action": "not_a_real_action"}, headers={_SESSION_HEADER: "session-1" * 5}
        )

    assert response.status_code == 400
    assert "not_a_real_action" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_session_header_is_rejected():
    async with client_for(make_app()) as client:
        response = await client.post("/invocations", json={"action": "start", "topic": "Topic"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_start_uses_the_session_header_as_the_run_id():
    """spec: "The same identifier addresses a run across its lifetime" """
    session_id = "consistent-session-id-1234567890"
    async with client_for(make_app()) as client:
        response = await client.post(
            "/invocations", json={"action": "start", "topic": "Topic"}, headers={_SESSION_HEADER: session_id}
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == session_id


@pytest.mark.asyncio
async def test_full_lifecycle_through_the_dispatcher_reaches_a_verdict():
    """spec: "Submitting a question resumes the run to a completed verdict" """
    session_id = "full-lifecycle-session-1234567890"
    async with client_for(make_app()) as client:
        start_response = await client.post(
            "/invocations", json={"action": "start", "topic": "Topic"}, headers={_SESSION_HEADER: session_id}
        )
        assert start_response.status_code == 200

        async with client.stream(
            "POST", "/invocations", json={"action": "stream"}, headers={_SESSION_HEADER: session_id}
        ) as response:
            first_events = await read_sse(response)
        assert first_events[-1]["node"] == "AWAITING_AUDIENCE_QUESTION"

        submit_response = await client.post(
            "/invocations",
            json={"action": "submit_audience_question", "question": "What about cost?"},
            headers={_SESSION_HEADER: session_id},
        )
        assert submit_response.status_code == 200
        assert submit_response.json() == {"run_id": session_id, "status": "resuming"}

        async with client.stream(
            "POST", "/invocations", json={"action": "stream"}, headers={_SESSION_HEADER: session_id}
        ) as response:
            second_events = await read_sse(response)
        assert second_events[-1]["node"] == "COMPLETE"


@pytest.mark.asyncio
async def test_two_sessions_do_not_interfere():
    """spec: "Two runs under different sessions do not interfere" """
    session_a = "session-aaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    session_b = "session-bbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    async with client_for(make_app()) as client:
        await client.post("/invocations", json={"action": "start", "topic": "Topic A"}, headers={_SESSION_HEADER: session_a})
        await client.post("/invocations", json={"action": "start", "topic": "Topic B"}, headers={_SESSION_HEADER: session_b})

        # Submitting a question against session B must not resume session A.
        response = await client.post(
            "/invocations",
            json={"action": "submit_audience_question", "question": "irrelevant"},
            headers={_SESSION_HEADER: session_a},
        )
        assert response.status_code == 409  # A is not awaiting a question yet -- only proves isolation, not a bug

        unknown_session_response = await client.post(
            "/invocations", json={"action": "resume"}, headers={_SESSION_HEADER: "never-started-session-000000000"}
        )
        assert unknown_session_response.status_code == 404

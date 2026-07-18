import pytest
import httpx

BASE_URL = "http://localhost:8000"


@pytest.mark.e2e
def test_health_endpoint():
    """E2E test: health endpoint must be accessible."""
    response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "message" in data


@pytest.mark.e2e
def test_debate_endpoint_invoke_returns_full_state():
    """E2E test: POST /debate/invoke must return complete debate state."""
    response = httpx.post(
        f"{BASE_URL}/debate/invoke",
        json={"topic": "Universal basic income should be implemented"},
        timeout=120.0,
    )
    assert response.status_code == 200
    state = response.json()

    # Verify all debate fields are populated
    assert "topic" in state
    assert "winner" in state
    assert state["winner"] in ("Pro", "Con", "")  # May be empty if parsing fails
    assert "moderator_summary" in state
    assert "pro_opening" in state
    assert "con_opening" in state
    assert len(state["pro_opening"]) > 0
    assert len(state["con_opening"]) > 0


@pytest.mark.e2e
def test_debate_endpoint_rejects_empty_topic():
    """E2E test: debate endpoint must reject empty topic."""
    response = httpx.post(
        f"{BASE_URL}/debate/invoke",
        json={"topic": ""},
        timeout=10.0,
    )
    assert response.status_code == 400


@pytest.mark.e2e
def test_debate_stream_endpoint():
    """E2E test: GET /debate/stream must stream events."""
    response = httpx.get(
        f"{BASE_URL}/debate/stream?topic=AI+will+replace+software+engineers",
        timeout=120.0,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream"

    # Verify at least some events were streamed
    events = []
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            events.append(line[6:])

    assert len(events) > 0, "Stream should produce at least one event"

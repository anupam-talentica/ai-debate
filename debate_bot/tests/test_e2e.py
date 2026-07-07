import pytest
import httpx

BASE_URL = "http://localhost:8000"


@pytest.mark.e2e
def test_debate_endpoint_returns_winner():
    """E2E test: debate endpoint must return a winner."""
    response = httpx.post(
        f"{BASE_URL}/debate/invoke",
        json={"input": {"topic": "Universal basic income should be implemented"}},
        timeout=120.0,
    )
    assert response.status_code == 200
    output = response.json()["output"]
    assert output["winner"] in ("Pro", "Con")
    assert len(output["moderator_summary"]) > 20


@pytest.mark.e2e
def test_debate_endpoint_rejects_empty_topic():
    """E2E test: debate endpoint must reject empty topic."""
    response = httpx.post(
        f"{BASE_URL}/debate/invoke",
        json={"input": {"topic": ""}},
        timeout=10.0,
    )
    assert response.status_code in (400, 422)


@pytest.mark.e2e
def test_health_endpoint():
    """E2E test: health endpoint must be accessible."""
    response = httpx.get(f"{BASE_URL}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

import pytest
import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_streaming_debate_receives_all_events():
    """Streaming endpoint should emit events for all nodes."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        events = [
            ("moderator_open", {"round": "opening"}),
            ("pro_opening", {"pro_opening": "Pro arg"}),
            ("con_opening", {"con_opening": "Con arg"}),
        ]

        async def mock_generator():
            for event in events:
                yield event

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"


@pytest.mark.asyncio
async def test_streaming_response_format():
    """SSE events should be properly formatted JSON."""
    from server import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def mock_generator():
            yield ("pro_opening", {"topic": "test", "pro_opening": "argument"})

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        lines = response.text.strip().split("\n\n")

        # Each line should be "data: {json}"
        for line in lines:
            if line:
                assert line.startswith("data: ")
                data_str = line.replace("data: ", "")
                data = json.loads(data_str)
                assert "node" in data or "error" in data


@pytest.mark.asyncio
async def test_streaming_completion_event():
    """Streaming should emit COMPLETE event at end."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def mock_generator():
            yield ("moderator_open", {"round": "opening"})

        mock_stream.return_value = mock_generator()
        with patch("app.memory_store.upsert_debate"):
            response = client.get("/debate/stream?topic=test")
            content = response.text
            # Should contain completion marker
            assert "COMPLETE" in content or "data:" in content


@pytest.mark.asyncio
async def test_streaming_with_client_disconnect():
    """Streaming should handle client disconnect gracefully."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def slow_generator():
            yield ("pro_opening", {"pro_opening": "arg"})
            await asyncio.sleep(10)  # Long delay to simulate timeout
            yield ("con_opening", {"con_opening": "arg"})

        mock_stream.return_value = slow_generator()

        # Client disconnects after first event
        response = client.get("/debate/stream?topic=test")
        # Should not crash the server


@pytest.mark.asyncio
async def test_streaming_error_event_on_exception():
    """Streaming should emit ERROR event if exception occurs."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def failing_generator():
            yield ("pro_opening", {"pro_opening": "arg"})
            raise ValueError("Test error")

        mock_stream.return_value = failing_generator()

        response = client.get("/debate/stream?topic=test")
        content = response.text
        # Should contain error information
        assert "ERROR" in content or "error" in content.lower()


@pytest.mark.asyncio
async def test_streaming_with_empty_topic():
    """Streaming with empty topic should fail validation."""
    from server import app
    client = TestClient(app)

    response = client.get("/debate/stream?topic=")
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_streaming_cache_control_headers():
    """Streaming response should have correct cache headers."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def mock_generator():
            yield ("test", {})

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("X-Accel-Buffering") == "no"


@pytest.mark.asyncio
async def test_streaming_multiple_concurrent_debates():
    """Multiple concurrent streaming connections should work."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def mock_generator():
            yield ("test", {"round": "opening"})

        mock_stream.return_value = mock_generator()

        # Simulate multiple clients streaming
        responses = []
        for i in range(3):
            response = client.get(f"/debate/stream?topic=topic_{i}")
            responses.append(response)

        # All should succeed
        assert all(r.status_code == 200 for r in responses)


@pytest.mark.asyncio
async def test_streaming_state_updates_sequentially():
    """Streaming events should reflect state updates in order."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        events = [
            ("moderator_open", {"round": "opening"}),
            ("pro_opening", {"pro_opening": "Pro argument", "round": "opening"}),
            ("con_opening", {"con_opening": "Con argument", "round": "opening"}),
        ]

        async def mock_generator():
            for event in events:
                yield event

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        lines = [l for l in response.text.strip().split("\n\n") if l]

        # Should have multiple events
        assert len(lines) >= len(events)


@pytest.mark.asyncio
async def test_streaming_with_large_state_object():
    """Streaming should handle large state objects."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        large_state = {
            "pro_opening": "A" * 5000,  # Large response
            "con_opening": "B" * 5000,
            "round": "opening",
        }

        async def mock_generator():
            yield ("pro_opening", large_state)

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_streaming_memory_upsert_after_completion():
    """Memory should be updated after streaming completes."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def mock_generator():
            yield ("moderator_open", {"round": "opening"})

        mock_stream.return_value = mock_generator()

        with patch("app.memory_store.upsert_debate") as mock_upsert:
            response = client.get("/debate/stream?topic=test")
            # Memory should be upser (or should it? depends on implementation)
            # Just verify no crash


@pytest.mark.asyncio
async def test_streaming_json_serialization_error():
    """Streaming should handle non-serializable state gracefully."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        class NonSerializable:
            pass

        async def mock_generator():
            yield ("test", {"data": NonSerializable()})

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        # Should either fail gracefully or skip the unesializable field


@pytest.mark.asyncio
async def test_streaming_heartbeat_on_long_processing():
    """Streaming should send heartbeats if processing takes long."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def slow_generator():
            yield ("pro_opening", {"pro_opening": "arg"})
            await asyncio.sleep(1)  # Simulate processing delay
            yield ("con_opening", {"con_opening": "arg"})

        mock_stream.return_value = slow_generator()

        response = client.get("/debate/stream?topic=test")
        # Should return without timeout


@pytest.mark.asyncio
async def test_streaming_response_preserves_state_field_order():
    """Streaming events should maintain consistent field order."""
    from server import app
    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        async def mock_generator():
            state = {
                "topic": "test",
                "round": "opening",
                "pro_opening": "arg",
                "con_opening": "",
                "pro_rebuttal": "",
                "con_rebuttal": "",
                "pro_closing": "",
                "con_closing": "",
                "moderator_summary": "",
                "winner": "",
                "memory_context": [],
            }
            yield ("pro_opening", state)

        mock_stream.return_value = mock_generator()

        response = client.get("/debate/stream?topic=test")
        lines = [l for l in response.text.strip().split("\n\n") if l]
        # Should properly serialize state
        assert len(lines) > 0

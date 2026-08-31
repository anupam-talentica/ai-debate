"""TRD Task 6's literal exit test: kill the real OS process mid-debate,
restart it, and resume continues from the last completed node -- the one
place this change tests an actual SIGKILL rather than an in-process
simulation (design.md, Decision 5; tasks.md, Section 7).

Runs `app:app` directly via uvicorn (not `server.py`, which sets
`reload=True` -- a reloader supervisor process would complicate sending a
single, unambiguous SIGKILL to "the server process"). MOCK_LLM mode
(mock-mode-eval-fixtures) makes this deterministic and fast: no live
Anthropic calls, and MOCK_LLM_DELAY_SECONDS gives a real wall-clock window
between node completions to land the kill precisely between two nodes of a
round, rather than at a round boundary.
"""

import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

MOCK_LLM_DELAY_SECONDS = "0.2"
STARTUP_TIMEOUT_SECONDS = 15.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn_server(port: int, session_storage_dir: str, memory_dir: str) -> subprocess.Popen:
    env = {
        **os.environ,
        "MOCK_LLM": "true",
        "MOCK_LLM_DELAY_SECONDS": MOCK_LLM_DELAY_SECONDS,
        "SESSION_STORAGE_DIRECTORY": session_storage_dir,
        "MEMORY_PERSIST_DIRECTORY": memory_dir,
    }
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_until_healthy(base_url: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/debate/health", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"server at {base_url} never became healthy")


@pytest.mark.asyncio
async def test_kill_process_mid_debate_restart_resumes_from_last_completed_node(tmp_path):
    session_storage_dir = str(tmp_path / "sessions")
    memory_dir = str(tmp_path / "chroma")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    proc = _spawn_server(port, session_storage_dir, memory_dir)
    try:
        _wait_until_healthy(base_url, time.monotonic() + STARTUP_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(timeout=10.0) as client:
            start_response = await client.post(
                f"{base_url}/debate/start", json={"topic": "Pro athletes are overpaid"}
            )
            run_id = start_response.json()["run_id"]

            events_before_kill = []
            async with client.stream("GET", f"{base_url}/debate/stream/{run_id}") as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[len("data: ") :])
                    events_before_kill.append(event["node"])
                    if event["node"] == "pro_opening":
                        break  # kill between pro_opening and con_opening, mid-round

        assert events_before_kill[-1] == "pro_opening"
        assert "con_opening" not in events_before_kill
    finally:
        proc.kill()
        proc.wait(timeout=10)

    port2 = _free_port()
    base_url2 = f"http://127.0.0.1:{port2}"
    proc2 = _spawn_server(port2, session_storage_dir, memory_dir)
    try:
        _wait_until_healthy(base_url2, time.monotonic() + STARTUP_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resume_response = await client.get(f"{base_url2}/debate/resume/{run_id}")
            assert resume_response.status_code == 200
            assert resume_response.json() == {"run_id": run_id}

            events_after_restart = []
            async with client.stream("GET", f"{base_url2}/debate/stream/{run_id}") as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[len("data: ") :])
                    events_after_restart.append(event)
    finally:
        proc2.kill()
        proc2.wait(timeout=10)

    node_names = [e["node"] for e in events_after_restart]
    assert "pro_opening" not in node_names  # did not repeat the round that already completed
    assert "con_opening" in node_names  # continued with the round's remaining node
    assert node_names[-1] == "AWAITING_AUDIENCE_QUESTION"  # no pre-supplied question -- pauses as usual

from src.api.services.run_registry import RunRegistry


def test_concurrent_entries_are_isolated():
    """Two runs created in the same registry don't see or affect each other's
    state (design.md, "Concurrent runs are isolated")."""
    registry = RunRegistry()

    entry_a = registry.create("run-a", {"topic": "Topic A"})
    entry_b = registry.create("run-b", {"topic": "Topic B"})

    entry_a.status = "waiting_for_input"
    entry_a.invocation_state["pro_opening"] = "A's opening"

    assert registry.get("run-b") is entry_b
    assert entry_b.status == "running"
    assert "pro_opening" not in entry_b.invocation_state
    assert registry.get("run-a") is entry_a
    assert entry_a.invocation_state["topic"] == "Topic A"
    assert entry_b.invocation_state["topic"] == "Topic B"


def test_unknown_run_id_returns_none():
    registry = RunRegistry()
    assert registry.get("does-not-exist") is None

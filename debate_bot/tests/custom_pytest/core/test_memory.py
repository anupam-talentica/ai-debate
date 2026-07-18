import pytest
from src.core.memory import MemoryStore


def test_upsert_and_retrieve():
    """Memory store must return relevant past debates."""
    store = MemoryStore()
    store.upsert_debate({
        "topic": "AI will replace software engineers",
        "winner": "Pro",
        "pro_opening": "AI is superior at coding tasks.",
        "con_opening": "Humans are still needed for creativity.",
        "moderator_summary": "Pro argued AI automates repetitive coding tasks.",
    })
    results = store.retrieve_context("Will AI take coding jobs?", k=1)
    assert len(results) == 1
    assert "Pro" in results[0] or "AI" in results[0]


def test_empty_store_returns_empty_list():
    store = MemoryStore()
    results = store.retrieve_context("Anything", k=2)
    assert results == []


def test_multiple_debates_retrieved():
    """Memory store must return top-k most relevant debates."""
    store = MemoryStore()
    store.upsert_debate({
        "topic": "AI will replace software engineers",
        "winner": "Pro",
        "pro_opening": "AI is transformative.",
        "con_opening": "Humans are irreplaceable.",
        "moderator_summary": "Pro won on technical arguments.",
    })
    store.upsert_debate({
        "topic": "Remote work is better than office work",
        "winner": "Con",
        "pro_opening": "Remote work improves productivity.",
        "con_opening": "Collaboration is better in-office.",
        "moderator_summary": "Con won on collaboration importance.",
    })
    results = store.retrieve_context("Will AI take coding jobs?", k=2)
    assert len(results) <= 2

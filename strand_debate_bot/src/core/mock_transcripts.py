"""Cached-transcript lookup for mock mode.

Ports `debate_bot/src/agents/mock.py::_load_transcript`'s exact matching
behavior onto the new codebase: case-insensitive exact `topic` match, with a
deterministic (filename-sorted) fallback -- logged, not silent -- so mock
mode still works for a topic that was never cached (design.md, Decision 2).
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "tests" / "mock_cache"


def load_transcript(topic: str, cache_dir: Path | None = None) -> dict[str, Any]:
    """Find a cached transcript matching `topic`, falling back to whichever
    cached transcript sorts first by filename if no topic matches."""
    cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    candidates = sorted(cache_dir.glob("*.json")) if cache_dir.is_dir() else []
    if not candidates:
        raise RuntimeError(
            f"MOCK_LLM is enabled but no cached transcripts exist at {cache_dir} -- "
            "copy fixture transcripts into this directory first."
        )

    topic_key = topic.strip().lower()
    for path in candidates:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("topic", "").strip().lower() == topic_key:
            return data

    logger.warning("MOCK_LLM: no cached transcript matches topic %r -- replaying %s", topic, candidates[0].name)
    return json.loads(candidates[0].read_text(encoding="utf-8"))

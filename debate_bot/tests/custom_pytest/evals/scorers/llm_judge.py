"""LLM-as-judge scorer for the argument-quality dimension.

A *stronger* model (``JUDGE_MODEL_NAME``, default ``claude-sonnet-5``) grades
debates produced by the default debate model (``claude-haiku-4-5-*``) so a
model never grades itself.

The judge returns 1-5 scores on four axes. Parsing is defensive: code fences
are stripped, and a JSON error triggers a single retry with a stricter
instruction. If the judge still fails, ``score_quality`` returns a result with
``ok=False`` and ``None`` axis scores so the overall run degrades gracefully
instead of crashing.
"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv

# Match the agent modules (pro.py / moderator.py): load .env at import so the
# judge picks up ANTHROPIC_API_KEY regardless of import order.
load_dotenv()

# Bare names used only when talking to the judge LLM (prompt schema below).
_RAW_AXES = ["relevance", "persuasiveness", "rebuttal_engagement", "moderator_soundness"]

# Report-facing axis names. Prefixed so a reader scanning a scorecard can't
# mistake a 1(poor)-5(excellent) LLM-judge score for a deterministic pass/fail
# bit, where 1 means success. Everything downstream (report.py, evaluators.py,
# test_evals.py) imports and uses these, not the raw names above.
AXES = [f"judge_{axis}" for axis in _RAW_AXES]

_JUDGE = None


def _get_judge():
    """Lazily construct the judge LLM so importing this module never needs an
    API key (keeps deterministic-only runs and test collection cheap)."""
    global _JUDGE
    if _JUDGE is None:
        from langchain_anthropic import ChatAnthropic

        # Note: temperature is intentionally NOT set — it is deprecated for
        # newer judge models (e.g. claude-sonnet-5) and raises a 400.
        _JUDGE = ChatAnthropic(
            model=os.getenv("JUDGE_MODEL_NAME", "claude-sonnet-5"),
        )
    return _JUDGE


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of a possibly-chatty judge response."""
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to the first {...} block found anywhere in the text.
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _build_prompt(s: dict) -> str:
    example = ", ".join(
        f'"{axis}": {{"score": <1-5 integer>, "reason": "<one sentence, cite '
        f'specific evidence from the transcript>"}}'
        for axis in _RAW_AXES
    )
    return (
        "You are an impartial debate judge. Score the debate below from 1 (poor) "
        "to 5 (excellent) on each axis. For each axis, also give a one-sentence "
        "reason that cites specific evidence from the transcript (e.g. a quoted "
        "or paraphrased point) — this is what makes the score low or high. "
        f"Return ONLY a JSON object of this exact shape, no prose outside it:\n"
        f"{{{example}}}\n\n"
        f"Topic: {s.get('topic', '')}\n\n"
        f"Pro opening:\n{s.get('pro_opening', '')}\n\n"
        f"Con opening:\n{s.get('con_opening', '')}\n\n"
        f"Con rebuttal (should directly engage Pro's argument):\n"
        f"{s.get('con_rebuttal', '')}\n\n"
        f"Moderator decision:\n{s.get('moderator_summary', '')}\n\n"
        "Axes:\n"
        "- relevance: do the arguments stay on the stated topic?\n"
        "- persuasiveness: are the arguments specific, well-reasoned, compelling?\n"
        "- rebuttal_engagement: does the rebuttal address the other side's actual points?\n"
        "- moderator_soundness: is the moderator's decision justified by the debate?\n"
    )


def _normalize(raw: dict) -> dict:
    """Coerce parsed values to ints in [1,5] plus a reason string; missing
    axis → None. Accepts both the current {"score", "reason"} shape and the
    older bare-int shape, so a judge reply that skips reasoning still parses.

    ``raw`` is keyed by the bare names the judge was asked for (_RAW_AXES);
    the returned dict is keyed by the prefixed, report-facing names (AXES)."""
    out = {"ok": True, "error": None}
    for raw_axis, axis in zip(_RAW_AXES, AXES):
        entry = raw.get(raw_axis)
        score, reason = entry, None
        if isinstance(entry, dict):
            score = entry.get("score")
            reason = entry.get("reason")
        try:
            score = int(round(float(score)))
            score = max(1, min(5, score))
        except (TypeError, ValueError):
            score = None
        out[axis] = score
        out[f"{axis}_reason"] = reason if isinstance(reason, str) and reason.strip() else None
    return out


async def score_quality(s: dict) -> dict:
    """Judge one debate. Never raises — returns ok=False on failure."""
    judge = _get_judge()
    prompt = _build_prompt(s)

    last_err = None
    for attempt in range(2):
        try:
            ask = prompt if attempt == 0 else (
                prompt + "\nIMPORTANT: your previous reply was not valid JSON. "
                "Reply with ONLY the JSON object, nothing else."
            )
            resp = await judge.ainvoke(ask)
            content = resp.content
            if isinstance(content, list):  # some SDK versions return blocks
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return _normalize(_extract_json(content))
        except Exception as exc:  # JSON error, API error, etc.
            last_err = exc

    failed = {"ok": False, "error": str(last_err)}
    for axis in AXES:
        failed[axis] = None
        failed[f"{axis}_reason"] = None
    return failed

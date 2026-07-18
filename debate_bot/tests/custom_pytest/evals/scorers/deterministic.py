"""Deterministic (no-LLM) scorers for the correctness / robustness dimension.

Every check is a pure function of the final debate state dict returned by
``app.run_debate``. All results are booleans or numbers so they are cheap,
reproducible, and free.

Word-count caps come from ``src/core/prompts.py``:
    opening  ≤ 250 words
    rebuttal ≤ 130 words
    closing  ≤ 100 words

The winner-validity check exercises the brittle parser in
``src/agents/moderator.py:40-53``.
"""

from __future__ import annotations

# Argument fields every complete debate must populate.
ARG_FIELDS = [
    "pro_opening",
    "con_opening",
    "pro_rebuttal",
    "con_rebuttal",
    "pro_closing",
    "con_closing",
]

# Caps from prompts.py (a small tolerance is applied when scoring so that a
# one- or two-word overshoot is flagged but the model gets credit for staying
# roughly on budget). The raw caps are kept here for reference.
OPENING_CAP = 250
REBUTTAL_CAP = 130
CLOSING_CAP = 100


def word_count(text: str | None) -> int:
    """Whitespace word count; ``None``/empty → 0."""
    if not text:
        return 0
    return len(text.split())


def score_deterministic(s: dict) -> dict:
    """Compute all deterministic metrics for a final debate state.

    Returns a flat dict of booleans / numbers. Missing keys are treated as
    empty so a partially-failed debate still scores without raising. Beyond
    the pass/fail booleans, a few diagnostic fields (``missing_fields``,
    ``mod_mentions_*``, both sides' word counts) are included purely so a
    report can explain *why* a check passed or failed without re-running the
    debate.
    """
    missing_fields = [f for f in ARG_FIELDS if not s.get(f)]

    summary = s.get("moderator_summary") or ""
    lower_summary = summary.lower()
    mentions_pro = "pro" in lower_summary
    mentions_con = "con" in lower_summary
    declares_winner = any(kw in lower_summary for kw in ("winner", "declare", "wins"))

    return {
        # moderator.py:40-53 — must resolve to a valid side.
        "winner_valid": s.get("winner") in ("Pro", "Con"),
        # No empty argument fields.
        "all_fields": not missing_fields,
        "missing_fields": missing_fields,
        # Word-count caps (checked on both sides; whole check fails if either
        # side blows the budget).
        "opening_wc_ok": (
            word_count(s.get("pro_opening")) <= OPENING_CAP
            and word_count(s.get("con_opening")) <= OPENING_CAP
        ),
        "rebuttal_wc_ok": (
            word_count(s.get("pro_rebuttal")) <= REBUTTAL_CAP
            and word_count(s.get("con_rebuttal")) <= REBUTTAL_CAP
        ),
        "closing_wc_ok": (
            word_count(s.get("pro_closing")) <= CLOSING_CAP
            and word_count(s.get("con_closing")) <= CLOSING_CAP
        ),
        # Moderator summary structure: references both sides and declares a
        # winner (the MODERATOR_DECISION prompt asks for exactly these 3 parts).
        "mod_3part": mentions_pro and mentions_con and declares_winner,
        "mod_mentions_pro": mentions_pro,
        "mod_mentions_con": mentions_con,
        "mod_declares_winner": declares_winner,
        # Raw word counts (numbers, useful in the scorecard for debugging).
        "pro_opening_wc": word_count(s.get("pro_opening")),
        "con_opening_wc": word_count(s.get("con_opening")),
        "pro_rebuttal_wc": word_count(s.get("pro_rebuttal")),
        "con_rebuttal_wc": word_count(s.get("con_rebuttal")),
        "pro_closing_wc": word_count(s.get("pro_closing")),
        "con_closing_wc": word_count(s.get("con_closing")),
    }

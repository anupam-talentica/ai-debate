"""Test report generation: a narrative Test Summary Report + results.json.

Structure follows the standard test-summary-report shape (objective, test
environment, test data, per-test-case results with rationale, defect log,
conclusion) so a reader can see *what* was tested, *how*, against *which*
sample data, and *why* each check passed or failed — without having to open
the source or re-run anything.

Each dataset topic (``tests/custom_pytest/evals/datasets/topics.jsonl``) is
treated as one test case; each deterministic check / judge axis is one
assertion within it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .scorers.deterministic import ARG_FIELDS, CLOSING_CAP, OPENING_CAP, REBUTTAL_CAP
from .scorers.llm_judge import AXES

# Boolean deterministic metrics reported as pass-rates.
DET_BOOL_METRICS = [
    "winner_valid",
    "all_fields",
    "opening_wc_ok",
    "rebuttal_wc_ok",
    "closing_wc_ok",
    "mod_3part",
]

WORD_CAPS = {"opening": OPENING_CAP, "rebuttal": REBUTTAL_CAP, "closing": CLOSING_CAP}

# Static metadata describing each check, used only for reporting — the checks
# themselves live in scorers/deterministic.py.
CHECKS = {
    "winner_valid": {
        "label": "Winner resolves to Pro/Con",
        "objective": "The moderator's declared winner must resolve to exactly "
                     "'Pro' or 'Con' so downstream consumers (UI, analytics) can rely on it.",
        "method": "Parse state['winner'] — produced by the keyword/regex extraction "
                  "in moderator.py:40-53 — and check it is exactly 'Pro' or 'Con'.",
    },
    "all_fields": {
        "label": "All transcript fields populated",
        "objective": "Every stage of the debate (openings, rebuttals, closings for "
                     "both sides) must produce non-empty output, ruling out silent "
                     "LangGraph node failures.",
        "method": f"Check truthiness of all {len(ARG_FIELDS)} argument fields "
                  f"({', '.join(ARG_FIELDS)}) in the final state.",
    },
    "opening_wc_ok": {
        "label": "Opening statements within word cap",
        "objective": f"Both sides' opening statements must respect the "
                     f"{WORD_CAPS['opening']}-word cap defined in prompts.py.",
        "method": f"Whitespace word-count pro_opening and con_opening; pass if "
                  f"both are <= {WORD_CAPS['opening']}.",
    },
    "rebuttal_wc_ok": {
        "label": "Rebuttals within word cap",
        "objective": f"Both sides' rebuttals must respect the "
                     f"{WORD_CAPS['rebuttal']}-word cap defined in prompts.py.",
        "method": f"Whitespace word-count pro_rebuttal and con_rebuttal; pass if "
                  f"both are <= {WORD_CAPS['rebuttal']}.",
    },
    "closing_wc_ok": {
        "label": "Closings within word cap",
        "objective": f"Both sides' closing statements must respect the "
                     f"{WORD_CAPS['closing']}-word cap defined in prompts.py.",
        "method": f"Whitespace word-count pro_closing and con_closing; pass if "
                  f"both are <= {WORD_CAPS['closing']}.",
    },
    "mod_3part": {
        "label": "Moderator summary is structurally complete",
        "objective": "The moderator's decision should reference both Pro's and "
                     "Con's positions and declare a winner (a 3-part decision).",
        "method": "Lowercase substring check for 'pro', 'con', and one of "
                  "'winner' / 'declare' / 'wins' in moderator_summary.",
    },
}

JUDGE_AXES = {
    "judge_relevance": "Do the arguments stay on the stated topic?",
    "judge_persuasiveness": "Are the arguments specific, well-reasoned, and compelling?",
    "judge_rebuttal_engagement": "Does the rebuttal address the other side's actual points?",
    "judge_moderator_soundness": "Is the moderator's decision justified by the debate transcript?",
}

QUALITY_GOOD = 4       # score >= this -> Good
QUALITY_MARGINAL = 3   # score >= this (and < GOOD) -> Marginal; below -> Poor

# Known root causes for checks that fail systematically, keyed by check id.
# Kept short and specific; only filled in for issues already diagnosed against
# this codebase. Checks without an entry fall back to the per-row reason.
KNOWN_ROOT_CAUSES = {
    "winner_valid": (
        "moderator.py:40-53 extracts the winner with a keyword/regex scan but "
        "never strips markdown emphasis or trailing punctuation from the raw "
        "LLM output (e.g. '**Con**' survives as 'Con**'), so the result rarely "
        "matches 'Pro'/'Con' exactly."
    ),
    "rebuttal_wc_ok": (
        "the rebuttal prompt's 130-word cap (prompts.py) is a soft instruction "
        "to the model, not an enforced truncation — the model regularly "
        "overshoots it."
    ),
}


def _fmt_cell(v) -> str:
    if v is True:
        return "✅"
    if v is False:
        return "❌"
    if v is None:
        return "—"
    return str(v)


def _mean(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _pass_rate(values: list) -> float:
    bools = [v for v in values if isinstance(v, bool)]
    if not bools:
        return 0.0
    return sum(1 for v in bools if v) / len(bools)


def build_summary(rows: list[dict]) -> dict:
    """Aggregate per-metric pass-rates (booleans) and means (judge axes)."""
    summary = {"n_topics": len(rows), "pass_rates": {}, "means": {}}
    for metric in DET_BOOL_METRICS:
        summary["pass_rates"][metric] = round(
            _pass_rate([r.get(metric) for r in rows]), 3
        )
    for axis in AXES:
        m = _mean([r.get(axis) for r in rows])
        summary["means"][axis] = round(m, 2) if m is not None else None
    n_judged = sum(1 for r in rows if r.get("judge_ok"))
    summary["judge_success_rate"] = round(n_judged / len(rows), 3) if rows else 0.0
    return summary


# ---------------------------------------------------------------------------
# Per-check, per-row explanations ("why did this pass/fail?")
# ---------------------------------------------------------------------------

def _wc_reason(stage: str, row: dict, passed: bool) -> tuple[str, str]:
    cap = WORD_CAPS[stage]
    pro = row.get(f"pro_{stage}_wc")
    con = row.get(f"con_{stage}_wc")
    pro_s = f"{pro}w" if pro is not None else "n/a"
    con_s = f"{con}w" if con is not None else "n/a (older run — con-side count not captured)"
    actual = f"Pro {pro_s} / Con {con_s} (cap {cap}w)"
    if passed:
        return actual, "both sides stayed within the cap."
    over = []
    if isinstance(pro, int) and pro > cap:
        over.append(f"Pro exceeds by {pro - cap}w")
    if isinstance(con, int) and con > cap:
        over.append(f"Con exceeds by {con - cap}w")
    reason = "; ".join(over) if over else f"one or both sides exceed the {cap}w cap."
    return actual, reason


def explain_check(check_id: str, row: dict) -> dict:
    """Return {"expected", "actual", "reason"} describing this row's result
    for this check, using whatever diagnostic fields are present."""
    passed = row.get(check_id)

    if check_id == "winner_valid":
        winner = row.get("winner")
        expected = "winner is exactly 'Pro' or 'Con'"
        actual = f"winner = {winner!r}"
        reason = ("resolves cleanly to a valid side." if passed else
                   "does not exactly match 'Pro' or 'Con' — likely leftover "
                   "formatting (e.g. markdown bold) from the raw model output.")
        return {"expected": expected, "actual": actual, "reason": reason}

    if check_id == "all_fields":
        missing = row.get("missing_fields")
        expected = f"all {len(ARG_FIELDS)} transcript fields non-empty"
        if passed:
            return {"expected": expected, "actual": "all fields present",
                     "reason": "every stage produced output."}
        if missing:
            return {"expected": expected, "actual": f"missing: {', '.join(missing)}",
                     "reason": "one or more LangGraph stages produced no output."}
        return {"expected": expected, "actual": "at least one field empty",
                 "reason": "which field(s) is not available for this run "
                           "(older results predate the missing_fields diagnostic)."}

    if check_id in ("opening_wc_ok", "rebuttal_wc_ok", "closing_wc_ok"):
        stage = check_id.split("_")[0]
        actual, reason = _wc_reason(stage, row, bool(passed))
        cap = WORD_CAPS[stage]
        return {"expected": f"both sides <= {cap}w", "actual": actual, "reason": reason}

    if check_id == "mod_3part":
        parts = {
            "mentions Pro": row.get("mod_mentions_pro"),
            "mentions Con": row.get("mod_mentions_con"),
            "declares a winner": row.get("mod_declares_winner"),
        }
        expected = "summary mentions Pro, mentions Con, and declares a winner"
        if passed:
            return {"expected": expected, "actual": "all 3 parts present", "reason": "—"}
        if any(v is not None for v in parts.values()):
            missing_parts = [name for name, v in parts.items() if v is False]
            return {"expected": expected,
                     "actual": f"missing: {', '.join(missing_parts) or 'unknown'}",
                     "reason": "moderator summary omitted one of the 3 required parts."}
        return {"expected": expected, "actual": "not all 3 parts present",
                 "reason": "sub-part breakdown not available for this run "
                           "(older results predate the mod_mentions_* diagnostic)."}

    return {"expected": "—", "actual": _fmt_cell(passed), "reason": "—"}


def _quality_verdict(score: int | float | None) -> str:
    if score is None:
        return "n/a"
    if score >= QUALITY_GOOD:
        return "Good"
    if score >= QUALITY_MARGINAL:
        return "Marginal"
    return "Poor"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_header(summary: dict) -> list[str]:
    debate_model = os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001")
    judge_model = os.getenv("JUDGE_MODEL_NAME", "claude-sonnet-5")
    lines = [
        "# Debate Bot — Eval Test Report\n",
        "## 1. Objective\n",
        "Verify that the LangGraph debate pipeline (opening → rebuttal → closing → "
        "moderator decision) produces complete, well-formed, on-topic debates across "
        "a range of topics, including adversarial edge cases designed to stress known "
        "weak points (winner parsing, word-count enforcement, argument continuity).\n",
        "## 2. Test Environment\n",
        f"- Debate model under test: `{debate_model}`\n"
        f"- Judge model (grades quality, never the same model that debated): `{judge_model}`\n"
        f"- Harness: `python -m tests.custom_pytest.evals.run_evals`\n"
        f"- Topics run this pass: **{summary['n_topics']}**\n",
    ]
    return lines


def _render_test_data(rows: list[dict]) -> list[str]:
    lines = ["## 3. Test Data\n",
             "One dataset topic = one test case. `note` records why the topic is in "
             "the dataset (baseline coverage vs. a specific edge case being stressed).\n",
             "| id | topic | why this topic exists |",
             "|---|---|---|"]
    for r in rows:
        note = r.get("note") or "baseline coverage"
        lines.append(f"| {r.get('id')} | {r.get('topic')} | {note} |")
    lines.append("")
    return lines


def _render_results_overview(summary: dict) -> list[str]:
    lines = ["## 4. Results Overview\n",
              f"Judge success rate: **{summary['judge_success_rate']:.0%}** "
              f"(judge calls that returned parseable scores)\n",
              "| check | pass-rate |",
              "|---|---|"]
    for metric in DET_BOOL_METRICS:
        rate = summary["pass_rates"][metric]
        lines.append(f"| {CHECKS[metric]['label']} | {rate:.0%} |")
    lines.append("")
    lines.append("| quality axis | mean (1-5) |")
    lines.append("|---|---|")
    for axis in AXES:
        mean = summary["means"][axis]
        lines.append(f"| {axis} | {mean if mean is not None else '—'} |")
    lines.append("")
    return lines


def _render_test_case(row: dict) -> list[str]:
    tc_id = row.get("id")
    topic = row.get("topic")
    note = row.get("note")

    lines = [f"### Test case: `{tc_id}`\n"]
    lines.append(f"**Objective:** {note or 'Run a baseline, well-formed debate end to end.'}\n")
    lines.append(f"**Test data (input topic):** \"{topic}\"\n")
    lines.append(
        "**Method:** ran a full debate via `app.run_debate(topic)` through the "
        "LangGraph pipeline, then scored the resulting state deterministically "
        "and via the LLM judge.\n"
    )

    if row.get("run_error"):
        lines.append(f"**Result: ❌ ERROR** — the debate run itself raised: "
                      f"`{row['run_error']}`. No downstream checks could run.\n")
        return lines

    lines.append("**Assertions (deterministic):**\n")
    lines.append("| check | expected | actual | result | why |")
    lines.append("|---|---|---|---|---|")
    for check_id in DET_BOOL_METRICS:
        passed = row.get(check_id)
        info = explain_check(check_id, row)
        lines.append(
            f"| {CHECKS[check_id]['label']} | {info['expected']} | {info['actual']} "
            f"| {_fmt_cell(passed)} | {info['reason']} |"
        )
    lines.append("")

    lines.append("**Quality ratings (LLM judge, 1-5):**\n")
    if row.get("judge_ok"):
        lines.append("| axis | rubric | score | verdict | why |")
        lines.append("|---|---|---|---|---|")
        for axis in AXES:
            score = row.get(axis)
            reason = row.get(f"{axis}_reason") or "—"
            lines.append(f"| {axis} | {JUDGE_AXES[axis]} | {score if score is not None else '—'} "
                         f"| {_quality_verdict(score)} | {reason} |")
    else:
        lines.append("_Judge call failed for this topic — no quality scores available._")
    lines.append("")

    return lines


def _render_defects(rows: list[dict]) -> list[str]:
    lines = ["## 6. Defects Found\n"]
    any_defect = False
    for check_id in DET_BOOL_METRICS:
        failing = [r for r in rows if r.get(check_id) is False]
        if not failing:
            continue
        any_defect = True
        ids = ", ".join(f"`{r.get('id')}`" for r in failing)
        rate = len(failing) / len(rows)
        lines.append(f"### {CHECKS[check_id]['label']} — failed {len(failing)}/{len(rows)} "
                      f"({rate:.0%})\n")
        lines.append(f"Affected test cases: {ids}\n")
        cause = KNOWN_ROOT_CAUSES.get(check_id)
        if cause:
            lines.append(f"**Likely root cause:** {cause}\n")
        else:
            lines.append("**Root cause:** see per-test-case \"why\" column above; no "
                          "systemic cause has been diagnosed for this check yet.\n")
    if not any_defect:
        lines.append("No deterministic check failures this run.\n")
    return lines


def _render_conclusion(summary: dict) -> list[str]:
    critical_fail = summary["pass_rates"].get("winner_valid", 1.0) < 0.9
    lines = ["## 7. Conclusion\n"]
    if critical_fail:
        lines.append(
            "**Overall: FAIL.** `winner_valid` is below the 90% CI gate "
            "(`test_evals.py`) — this pipeline is not ready to rely on the "
            "moderator's winner field until the parser is fixed.\n"
        )
    else:
        lines.append("**Overall: PASS.** No blocking defects against the CI gate.\n")
    return lines


def render_markdown(rows: list[dict], summary: dict) -> str:
    lines: list[str] = []
    lines += _render_header(summary)
    lines += _render_test_data(rows)
    lines += _render_results_overview(summary)
    lines.append("## 5. Detailed Test Case Results\n")
    for row in rows:
        lines += _render_test_case(row)
    lines += _render_defects(rows)
    lines += _render_conclusion(summary)
    return "\n".join(lines)


def print_scorecard(rows: list[dict], out_path: str | Path | None = None) -> dict:
    """Print the narrative test report, write results.json + TEST_REPORT.md.

    Returns the summary dict (unchanged shape, so the CI gate in
    test_evals.py keeps working)."""
    summary = build_summary(rows)
    report_md = render_markdown(rows, summary)
    print("\n" + report_md + "\n")

    if out_path is None:
        out_path = Path(__file__).parent / "results.json"
    out_path = Path(out_path)
    payload = {"summary": summary, "rows": rows}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}")

    report_path = out_path.parent / "TEST_REPORT.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Wrote {report_path}")

    return summary

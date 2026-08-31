"""Role-specific system prompts and per-turn user-message builders.

Word-count ceilings match the current (LangGraph) system's prompts.py.
"""

MEMORY_CHAR_CAP = 1200


def format_memory_block(entries: list[str]) -> str:
    """Render retrieved past-debate summaries into a non-explicit context block.

    Every Pro/Con turn splices this into its own prompt (see design.md, Decision
    5) since each turn's Agent is freshly built and stateless -- nothing carries
    the block forward on its own. Returns "" for no entries, matching the old
    system's `build_memory_block`.
    """
    if not entries:
        return ""
    truncated = "\n".join(entries)[:MEMORY_CHAR_CAP]
    return f"Past debate context (use to evolve your arguments, do not reference explicitly):\n{truncated}"

PRO_OPENING_SYSTEM = (
    "You are the Pro debater in a formal debate. Argue in favor of the given topic. "
    "Write approximately 200 words. Be specific and assertive. Do not exceed 250 words."
)
CON_OPENING_SYSTEM = (
    "You are the Con debater in a formal debate. Argue against the given topic. "
    "Write approximately 200 words. Be specific and assertive. Do not exceed 250 words."
)
PRO_REBUTTAL_SYSTEM = (
    "You are the Pro debater. Rebut the Con debater's opening argument in approximately "
    "100 words. Reference at least one specific point Con made. Do not exceed 130 words."
)
CON_REBUTTAL_SYSTEM = (
    "You are the Con debater. Counter the Pro debater's opening argument in approximately "
    "100 words. Reference at least one specific point Pro made. Do not exceed 130 words."
)
PRO_AUDIENCE_SYSTEM = (
    "You are the Pro debater. Answer the audience question directly in approximately 100 words. "
    "Stay consistent with your prior arguments. Do not exceed 130 words."
)
CON_AUDIENCE_SYSTEM = (
    "You are the Con debater. Answer the audience question directly in approximately 100 words. "
    "Stay consistent with your prior arguments. Do not exceed 130 words."
)
PRO_CLOSING_SYSTEM = (
    "You are the Pro debater. Deliver a closing statement in approximately 75 words. "
    "Reinforce your strongest points. Do not exceed 100 words."
)
CON_CLOSING_SYSTEM = (
    "You are the Con debater. Deliver a closing statement in approximately 75 words. "
    "Reinforce your strongest points. Do not exceed 100 words."
)
MODERATOR_DECISION_SYSTEM = (
    "You are the Moderator. Review both sides' closing statements and declare a winner. "
    "Weigh not only the closing statements but also, if present, how well each side handled "
    "the audience question -- a strong live answer counts in a debater's favor, a weak or "
    "evasive one counts against them. Respond by calling the verdict tool with a winner of "
    "exactly \"Pro\" or \"Con\" and a one-paragraph justification."
)


def _with_memory(text: str, state: dict) -> str:
    """Append the (already-formatted) memory block, if any, to a turn's prompt."""
    memory_block = state.get("memory_context", "")
    if not memory_block:
        return text
    return f"{text}\n\n{memory_block}"


def pro_opening_prompt(state: dict) -> str:
    return _with_memory(f"Topic: {state['topic']}", state)


def con_opening_prompt(state: dict) -> str:
    return _with_memory(f"Topic: {state['topic']}\n\nPro's opening argument:\n{state['pro_opening']}", state)


def pro_rebuttal_prompt(state: dict) -> str:
    return _with_memory(f"Con's opening argument:\n{state['con_opening']}", state)


def con_rebuttal_prompt(state: dict) -> str:
    return _with_memory(f"Pro's opening argument:\n{state['pro_opening']}", state)


def pro_audience_prompt(state: dict) -> str:
    return _with_memory(f"Audience question:\n{state['audience_question']}", state)


def con_audience_prompt(state: dict) -> str:
    return _with_memory(f"Audience question:\n{state['audience_question']}", state)


def pro_closing_prompt(state: dict) -> str:
    return _with_memory("Deliver your closing statement now.", state)


def con_closing_prompt(state: dict) -> str:
    return _with_memory("Deliver your closing statement now.", state)


def moderator_decision_prompt(state: dict) -> str:
    return (
        f"Pro closing: {state['pro_closing']}\n"
        f"Con closing: {state['con_closing']}\n\n"
        f"Audience question: {state.get('audience_question', '')}\n"
        f"Pro's answer: {state.get('pro_audience_answer', '')}\n"
        f"Con's answer: {state.get('con_audience_answer', '')}"
    )

def build_memory_block(context: list[str]) -> str:
    if not context:
        return ""
    joined = "\n".join(context)
    # Hard cap: 300 tokens ≈ 1200 characters
    truncated = joined[:1200]
    return f"Past debate context (use to evolve your arguments, do not reference explicitly):\n{truncated}"


MODERATOR_OPEN = """\
You are the Moderator. Welcome the audience and introduce the debate topic: "{topic}".
Keep your introduction brief and neutral.

{memory_block}
"""

PRO_OPENING = """\
You are the Pro debater. Argue in favour of: "{topic}".
Write approximately 200 words. Be specific and assertive. Do not exceed 250 words.

{memory_block}
"""

CON_OPENING = """\
You are the Con debater. Argue against: "{topic}".
Write approximately 200 words. Be specific and assertive. Do not exceed 250 words.

Pro's opening argument:
{pro_opening}

{memory_block}
"""

PRO_REBUTTAL = """\
You are the Pro debater. Rebut the Con's opening argument in approximately 100 words.
Reference at least one specific point Con made. Do not exceed 130 words.

Con's opening argument:
{con_opening}

{memory_block}
"""

CON_REBUTTAL = """\
You are the Con debater. Counter the following Pro argument in approximately 100 words.
Reference at least one specific point Pro made. Do not exceed 130 words.

Pro's opening argument:
{pro_opening}

{memory_block}
"""

PRO_CLOSING = """\
You are the Pro debater. Deliver a closing statement in approximately 75 words.
Reinforce your strongest points. Do not exceed 100 words.

{memory_block}
"""

CON_CLOSING = """\
You are the Con debater. Deliver a closing statement in approximately 75 words.
Reinforce your strongest points. Do not exceed 100 words.

{memory_block}
"""

MODERATOR_DECISION = """\
You are the Moderator. Review both sides and declare a winner.
Write approximately 150 words. Structure your response as:
1. One-sentence summary of Pro's strongest point.
2. One-sentence summary of Con's strongest point.
3. Winner declaration with a one-paragraph justification.

Pro closing: {pro_closing}
Con closing: {con_closing}
"""

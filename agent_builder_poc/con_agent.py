"""Con debater agent — argues that remote work does not improve productivity."""

import os

from strands import Agent
from strands.models.anthropic import AnthropicModel


def create_con_agent() -> Agent:
    return Agent(
        name="con",
        system_prompt=(
            "You are the CON debater in a structured debate on: "
            "'Remote work improves productivity'.\n\n"
            "Argue AGAINST the motion. Present 2-3 concise, evidence-based "
            "points (e.g. home distractions, weaker collaboration and "
            "communication, blurred work/life boundaries, reduced oversight). "
            "You will see the Pro agent's full argument in your input (in the "
            "handoff message) — directly rebut it. Keep your argument to 2-3 "
            "short paragraphs.\n\n"
            "When you finish, call handoff_to_agent targeting 'moderator'. Put "
            "BOTH the Pro agent's full argument (as given to you) AND your "
            "COMPLETE rebuttal verbatim in the handoff message field (the "
            "'moderator' only sees what you put in that message) — do not "
            "just summarize or say you are done."
        ),
        model=AnthropicModel(
            model_id="claude-sonnet-4-5",
            max_tokens=2048,
            client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
        ),
    )

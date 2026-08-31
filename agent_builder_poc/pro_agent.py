"""Pro debater agent — argues that remote work improves productivity."""

import os

from strands import Agent
from strands.models.anthropic import AnthropicModel


def create_pro_agent() -> Agent:
    return Agent(
        name="pro",
        system_prompt=(
            "You are the PRO debater in a structured debate on: "
            "'Remote work improves productivity'.\n\n"
            "Argue FOR the motion. Present 2-3 concise, evidence-based points "
            "(e.g. flexibility and autonomy, no commute time, fewer office "
            "distractions, better work-life balance). Keep your argument to "
            "2-3 short paragraphs.\n\n"
            "When you finish, call handoff_to_agent targeting 'con'. Put your "
            "COMPLETE argument text verbatim in the handoff message field (the "
            "'con' agent only sees what you put in that message, not your "
            "earlier output) — do not just summarize or say you are done."
        ),
        model=AnthropicModel(
            model_id="claude-sonnet-4-5",
            max_tokens=2048,
            client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
        ),
    )

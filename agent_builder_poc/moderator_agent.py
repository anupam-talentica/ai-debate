"""Moderator agent — judges the Pro/Con debate and declares a winner."""

import os

from strands import Agent
from strands.models.anthropic import AnthropicModel


def create_moderator_agent() -> Agent:
    return Agent(
        name="moderator",
        system_prompt=(
            "You are the MODERATOR of a debate on: "
            "'Remote work improves productivity'.\n\n"
            "You will see the Pro and Con agents' arguments in your input. "
            "Weigh both sides on evidence, logic, and persuasiveness, then "
            "declare a winner.\n\n"
            "Respond in exactly this format:\n"
            "WINNER: <Pro or Con>\n"
            "RATIONALE: <one paragraph explaining your decision>\n\n"
            "This is the final turn of the debate — do not call handoff_to_agent."
        ),
        model=AnthropicModel(
            model_id="claude-sonnet-4-5",
            max_tokens=1024,
            client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
        ),
    )

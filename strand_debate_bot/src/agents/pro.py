from strands import Agent
from strands.models.model import Model

from src.core.nodes import AgentTurnNode
from src.core.prompts import (
    PRO_OPENING_SYSTEM,
    PRO_REBUTTAL_SYSTEM,
    PRO_AUDIENCE_SYSTEM,
    PRO_CLOSING_SYSTEM,
    pro_opening_prompt,
    pro_rebuttal_prompt,
    pro_audience_prompt,
    pro_closing_prompt,
)


def pro_opening_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=PRO_OPENING_SYSTEM)
    return AgentTurnNode("pro_opening", agent, pro_opening_prompt, "pro_opening")


def pro_rebuttal_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=PRO_REBUTTAL_SYSTEM)
    return AgentTurnNode("pro_rebuttal", agent, pro_rebuttal_prompt, "pro_rebuttal")


def pro_addresses_question_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=PRO_AUDIENCE_SYSTEM)
    return AgentTurnNode("pro_addresses_question", agent, pro_audience_prompt, "pro_audience_answer")


def pro_closing_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=PRO_CLOSING_SYSTEM)
    return AgentTurnNode("pro_closing", agent, pro_closing_prompt, "pro_closing")

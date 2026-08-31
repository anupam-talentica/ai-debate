from strands import Agent
from strands.models.model import Model

from src.core.nodes import AgentTurnNode
from src.core.prompts import (
    CON_OPENING_SYSTEM,
    CON_REBUTTAL_SYSTEM,
    CON_AUDIENCE_SYSTEM,
    CON_CLOSING_SYSTEM,
    con_opening_prompt,
    con_rebuttal_prompt,
    con_audience_prompt,
    con_closing_prompt,
)


def con_opening_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=CON_OPENING_SYSTEM)
    return AgentTurnNode("con_opening", agent, con_opening_prompt, "con_opening")


def con_rebuttal_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=CON_REBUTTAL_SYSTEM)
    return AgentTurnNode("con_rebuttal", agent, con_rebuttal_prompt, "con_rebuttal")


def con_addresses_question_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=CON_AUDIENCE_SYSTEM)
    return AgentTurnNode("con_addresses_question", agent, con_audience_prompt, "con_audience_answer")


def con_closing_node(model: Model) -> AgentTurnNode:
    agent = Agent(model=model, system_prompt=CON_CLOSING_SYSTEM)
    return AgentTurnNode("con_closing", agent, con_closing_prompt, "con_closing")

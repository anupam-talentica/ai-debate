import os

from langgraph.graph import StateGraph, END
from src.core.state import DebateState
from src.agents.moderator import moderator_open, moderator_checkpoint, audience_question, moderator_decision
from src.agents.pro import pro_opening, pro_rebuttal, pro_addresses_question, pro_closing
from src.agents.con import con_opening, con_rebuttal, con_addresses_question, con_closing
from typing import Optional, Any

# MOCK_LLM=true replays a cached debate transcript instead of calling the real
# model (see src/agents/mock.py) — lets the UI/failover demo be exercised for
# free. moderator_open/moderator_checkpoint/audience_question never call the
# LLM even for real, so they're unaffected either way. pro_addresses_question/
# con_addresses_question are deliberately excluded from this swap even though
# they do call the LLM: the audience question is novel user input each run,
# so there's no scripted answer a cached transcript could replay — these two
# nodes always use the real model regardless of MOCK_LLM.
if os.getenv("MOCK_LLM", "false").strip().lower() in ("1", "true", "yes"):
    from src.agents.mock import (
        pro_opening, con_opening, pro_rebuttal, con_rebuttal,
        pro_closing, con_closing, moderator_decision,
    )


def route_after_checkpoint(state: DebateState) -> str:
    if state["round"] == "rebuttal":
        return "pro_rebuttal"
    elif state["round"] == "closing":
        return "pro_closing"
    else:  # "decision"
        return "moderator_decision"


def build_graph(memory_store: Optional[Any] = None, checkpointer: Optional[Any] = None):
    g = StateGraph(DebateState)

    g.add_node("moderator_open",       moderator_open)
    g.add_node("pro_opening",          pro_opening)
    g.add_node("con_opening",          con_opening)
    g.add_node("moderator_checkpoint", moderator_checkpoint)
    g.add_node("pro_rebuttal",         pro_rebuttal)
    g.add_node("con_rebuttal",         con_rebuttal)
    g.add_node("audience_question",        audience_question)
    g.add_node("pro_addresses_question",   pro_addresses_question)
    g.add_node("con_addresses_question",   con_addresses_question)
    g.add_node("pro_closing",          pro_closing)
    g.add_node("con_closing",          con_closing)
    g.add_node("moderator_decision",   moderator_decision)

    g.set_entry_point("moderator_open")

    g.add_edge("moderator_open",      "pro_opening")
    g.add_edge("pro_opening",         "con_opening")
    g.add_edge("con_opening",         "moderator_checkpoint")

    g.add_conditional_edges(
        "moderator_checkpoint",
        route_after_checkpoint,
        {
            "pro_rebuttal":       "pro_rebuttal",
            "pro_closing":        "pro_closing",
            "moderator_decision": "moderator_decision",
        },
    )

    g.add_edge("pro_rebuttal",        "con_rebuttal")
    g.add_edge("con_rebuttal",        "audience_question")
    g.add_edge("audience_question",       "pro_addresses_question")
    g.add_edge("pro_addresses_question",  "con_addresses_question")
    g.add_edge("con_addresses_question",  "moderator_checkpoint")

    g.add_edge("pro_closing",         "con_closing")
    g.add_edge("con_closing",         "moderator_checkpoint")

    g.add_edge("moderator_decision",  END)

    return g.compile(checkpointer=checkpointer)


debate_graph = build_graph()

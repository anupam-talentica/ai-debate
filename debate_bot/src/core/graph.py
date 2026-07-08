from langgraph.graph import StateGraph, END
from src.core.state import DebateState
from src.agents.moderator import moderator_open, moderator_checkpoint, moderator_decision
from src.agents.pro import pro_opening, pro_rebuttal, pro_closing
from src.agents.con import con_opening, con_rebuttal, con_closing
from typing import Optional, Any


def route_after_checkpoint(state: DebateState) -> str:
    if state["round"] == "rebuttal":
        return "pro_rebuttal"
    elif state["round"] == "closing":
        return "pro_closing"
    else:  # "decision"
        return "moderator_decision"


def build_graph(memory_store: Optional[Any] = None):
    g = StateGraph(DebateState)

    g.add_node("moderator_open",       moderator_open)
    g.add_node("pro_opening",          pro_opening)
    g.add_node("con_opening",          con_opening)
    g.add_node("moderator_checkpoint", moderator_checkpoint)
    g.add_node("pro_rebuttal",         pro_rebuttal)
    g.add_node("con_rebuttal",         con_rebuttal)
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
    g.add_edge("con_rebuttal",        "moderator_checkpoint")

    g.add_edge("pro_closing",         "con_closing")
    g.add_edge("con_closing",         "moderator_checkpoint")

    g.add_edge("moderator_decision",  END)

    return g.compile()


debate_graph = build_graph()

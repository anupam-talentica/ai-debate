from typing import TypedDict


class DebateState(TypedDict):
    topic: str
    round: str                 # "opening" | "rebuttal" | "closing" | "decision"
    pro_opening: str
    con_opening: str
    pro_rebuttal: str
    con_rebuttal: str
    pro_closing: str
    con_closing: str
    moderator_summary: str
    winner: str
    memory_context: list[str]  # top-2 retrieved past debate summaries (empty list on first run)

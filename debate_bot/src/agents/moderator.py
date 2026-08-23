import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.types import interrupt
from src.core.state import DebateState
from src.core.prompts import MODERATOR_DECISION

load_dotenv()

llm = ChatAnthropic(
    model=os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001"),
    streaming=True,
)

ROUND_TRANSITIONS = {
    "opening":  "rebuttal",
    "rebuttal": "closing",
    "closing":  "decision",
}


async def moderator_open(_state: DebateState) -> dict:
    return {"round": "opening"}


async def moderator_checkpoint(state: DebateState) -> dict:
    next_round = ROUND_TRANSITIONS.get(state["round"], "decision")
    return {"round": next_round}


async def audience_question(state: DebateState) -> dict:
    """Pause once for a single audience question after the rebuttal round.

    Skips the pause if a question was already pre-supplied (e.g. via the
    synchronous /invoke endpoint), so this node is idempotent to call with
    a question already in state.
    """
    if state.get("audience_question"):
        return {}
    question = interrupt("Submit an audience question for both debaters to address.")
    return {"audience_question": question}


async def moderator_decision(state: DebateState) -> dict:
    prompt = MODERATOR_DECISION.format(
        pro_closing=state["pro_closing"],
        con_closing=state["con_closing"],
        audience_question=state.get("audience_question", ""),
        pro_audience_answer=state.get("pro_audience_answer", ""),
        con_audience_answer=state.get("con_audience_answer", ""),
    )
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    full_text = "".join(chunks)

    winner = ""
    for line in full_text.splitlines():
        lower = line.lower()
        if "winner:" in lower or "winner is" in lower:
            # extract everything after the colon or "is"
            part = line.split(":", 1)[-1] if ":" in line else line
            winner = part.strip().split(".")[0].strip()
            break
    if not winner:
        # fallback: look for "Pro" or "Con" mentioned after "declare"
        for word in full_text.split():
            if word.rstrip(".,") in ("Pro", "Con"):
                winner = word.rstrip(".,")
                break

    return {"moderator_summary": full_text, "winner": winner}

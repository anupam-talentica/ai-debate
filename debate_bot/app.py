import asyncio
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.core.graph import build_graph
from src.core.memory import MemoryStore

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/debate_bot")
NODE_ID = os.getenv("NODE_ID") or f"local-{uuid.uuid4().hex[:8]}"

memory_store = MemoryStore()
graph = build_graph(memory_store)  # no checkpointer until init_checkpointer() runs at startup

_checkpointer_cm = None
checkpointer = None


async def init_checkpointer() -> None:
    """Create the Postgres checkpointer, create its tables if needed, and rebuild
    the graph to use it. Call once at process startup, before serving any debates."""
    global _checkpointer_cm, checkpointer, graph
    _checkpointer_cm = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
    checkpointer = await _checkpointer_cm.__aenter__()
    await checkpointer.setup()
    graph = build_graph(memory_store, checkpointer=checkpointer)


async def close_checkpointer() -> None:
    """Release the Postgres connection pool opened by init_checkpointer()."""
    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)


async def run_debate(topic: str, run_id: str | None = None, audience_question: str = "") -> dict:
    """Run a full debate and return the final state."""
    run_id = run_id or str(uuid.uuid4())
    initial_state = {
        "topic": topic,
        "round": "",
        "pro_opening": "",
        "con_opening": "",
        "pro_rebuttal": "",
        "con_rebuttal": "",
        "pro_closing": "",
        "con_closing": "",
        "moderator_summary": "",
        "winner": "",
        "memory_context": [],
        "audience_question": audience_question,
        "pro_audience_answer": "",
        "con_audience_answer": "",
    }
    config = {"configurable": {"thread_id": run_id}}
    final_state = await graph.ainvoke(initial_state, config=config)
    memory_store.upsert_debate(final_state)
    return final_state


if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI will replace software engineers"

    async def _main():
        await init_checkpointer()
        result = await run_debate(topic)
        print(f"\nWinner: {result['winner']}")
        print(f"Summary: {result['moderator_summary']}")
        await close_checkpointer()

    asyncio.run(_main())

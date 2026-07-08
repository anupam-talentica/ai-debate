import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from src.core.graph import build_graph
from src.core.memory import MemoryStore

memory_store = MemoryStore()
graph = build_graph(memory_store)


async def run_debate(topic: str) -> dict:
    """Run a full debate and return the final state."""
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
    }
    final_state = await graph.ainvoke(initial_state)
    memory_store.upsert_debate(final_state)
    return final_state


if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI will replace software engineers"
    result = asyncio.run(run_debate(topic))
    print(f"\nWinner: {result['winner']}")
    print(f"Summary: {result['moderator_summary']}")

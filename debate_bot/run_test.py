import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from graph import debate_graph
from memory import upsert_debate, retrieve_context

initial_state = {
    "topic": "Should AI be used in hiring?",
    "round": "opening",
    "pro_opening": "", "con_opening": "",
    "pro_rebuttal": "", "con_rebuttal": "",
    "pro_closing": "", "con_closing": "",
    "moderator_summary": "", "winner": "", "memory_context": [],
}

async def main():
    final = await debate_graph.ainvoke(initial_state)

    for field in ["pro_opening","con_opening","pro_rebuttal","con_rebuttal",
                  "pro_closing","con_closing","moderator_summary","winner"]:
        assert final[field], f"Field '{field}' is empty"

    print("All fields populated ✓")
    print("Winner:", final["winner"])
    print("Round at end:", final["round"])

    upsert_debate(final)
    print("Memory upsert OK ✓")

    context = retrieve_context("Should AI replace recruiters?")
    assert len(context) > 0, "Expected at least 1 similar past debate"
    print(f"Retrieved {len(context)} past debate(s) ✓")
    print("Snippet:", context[0][:100])

asyncio.run(main())

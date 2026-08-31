"""Run the Pro vs Con vs Moderator debate using the Strands Swarm primitive."""

# run_debate.py
#   ├─ pro_agent.py       → Agent(name="pro", model=AnthropicModel(...))
#   ├─ con_agent.py       → Agent(name="con", model=AnthropicModel(...))
#   ├─ moderator_agent.py → Agent(name="moderator", model=AnthropicModel(...))
#   └─ Swarm(nodes=[pro, con, moderator], entry_point=pro)
#        │
#        ▼
#   swarm(task)   # runs synchronously, returns a SwarmResult
#        │
#        ├─ pro turn       → writes argument → handoff_to_agent("con", full_text)
#        ├─ con turn       → writes rebuttal → handoff_to_agent("moderator", full_text)
#        └─ moderator turn → writes verdict  → (no handoff → swarm ends)

import sys

from strands.multiagent.swarm import Swarm

from con_agent import create_con_agent
from moderator_agent import create_moderator_agent
from pro_agent import create_pro_agent

DEFAULT_TOPIC = "Remote work improves productivity"


def run_debate(topic: str = DEFAULT_TOPIC) -> None:
    pro = create_pro_agent()
    con = create_con_agent()
    moderator = create_moderator_agent()

    swarm = Swarm(nodes=[pro, con, moderator], entry_point=pro)

    task = (
        f"Debate topic: '{topic}'.\n\n"
        "pro: present your opening argument FOR the motion, then hand off to con.\n"
        "con: present your rebuttal argument AGAINST the motion, then hand off to moderator.\n"
        "moderator: declare a winner with a one paragraph rationale, and do not hand off further."
    )

    result = swarm(task)

    print("=" * 80)
    print(f"DEBATE TRANSCRIPT: {topic}")
    print("=" * 80)

    for node in result.node_history:
        node_result = result.results[node.node_id]
        print(f"\n--- {node.node_id.upper()} ---\n")
        print(str(node_result))

    print("\n" + "=" * 80)
    print(f"Status: {result.status}")
    print("=" * 80)


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOPIC
    run_debate(topic)

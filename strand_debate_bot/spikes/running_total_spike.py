"""Throwaway spike (see openspec/changes/scaffolding-spike). Proves three
Strands mechanics the debate-bot migration depends on: graph-node interrupt/
resume with external input, cyclic hub revisits via conditional edges, and
invocation_state accumulation across those revisits. Not production code."""

import asyncio
from typing import Any

from strands.hooks import BeforeNodeCallEvent, HookProvider, HookRegistry
from strands.multiagent import GraphBuilder
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, Status


class NoOpNode(MultiAgentBase):
    """A named node the graph can route to/from; all real work happens via invocation_state."""

    def __init__(self, node_id: str) -> None:
        super().__init__()
        self.id = node_id

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        return MultiAgentResult(status=Status.COMPLETED)


class Adder(NoOpNode):
    async def invoke_async(self, task, invocation_state=None, **kwargs):
        invocation_state["total"] += 5
        invocation_state["trace"].append("adder: +5")
        return await super().invoke_async(task, invocation_state, **kwargs)


class Subtracter(NoOpNode):
    async def invoke_async(self, task, invocation_state=None, **kwargs):
        invocation_state["total"] -= 3
        invocation_state["trace"].append("subtracter: -3")
        return await super().invoke_async(task, invocation_state, **kwargs)


class Hub(NoOpNode):
    """Revisited once per round; a round counter in invocation_state picks the next branch."""

    async def invoke_async(self, task, invocation_state=None, **kwargs):
        invocation_state["round"] = invocation_state.get("round", 0) + 1
        if invocation_state["round"] == 4:
            invocation_state["final_total"] = invocation_state["total"]
            invocation_state["final_trace"] = list(invocation_state["trace"])
        return await super().invoke_async(task, invocation_state, **kwargs)


class HumanChoiceHook(HookProvider):
    """Interrupts before `human_choice` runs; applies the resumed op directly to the total."""

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeNodeCallEvent, self.ask)

    def ask(self, event: BeforeNodeCallEvent) -> None:
        if event.node_id != "human_choice":
            return
        response = event.interrupt(
            "running-total-human-choice", reason={"prompt": "add 2 or subtract 2?"}
        )
        op, amount = response.split()
        delta = int(amount) if op == "add" else -int(amount)
        event.invocation_state["total"] += delta
        event.invocation_state["trace"].append(f"human: {response}")


def build_graph():
    builder = GraphBuilder()

    builder.add_node(Hub("hub"), "hub")
    builder.add_node(Adder("adder"), "adder")
    builder.add_node(NoOpNode("human_choice"), "human_choice")
    builder.add_node(Subtracter("subtracter"), "subtracter")

    builder.add_edge(
        "hub", "adder",
        condition=lambda state, *, invocation_state, **kw: invocation_state.get("round") == 1,
    )
    builder.add_edge(
        "hub", "human_choice",
        condition=lambda state, *, invocation_state, **kw: invocation_state.get("round") == 2,
    )
    builder.add_edge(
        "hub", "subtracter",
        condition=lambda state, *, invocation_state, **kw: invocation_state.get("round") == 3,
    )
    builder.add_edge("adder", "hub")
    builder.add_edge("human_choice", "hub")
    builder.add_edge("subtracter", "hub")

    builder.set_entry_point("hub")
    builder.set_max_node_executions(20)
    builder.set_hook_providers([HumanChoiceHook()])
    return builder.build()


async def run(human_response: str) -> dict[str, Any]:
    graph = build_graph()
    invocation_state: dict[str, Any] = {"total": 10, "trace": [], "round": 0}

    result = await graph.invoke_async("run", invocation_state=invocation_state)
    resumes = 0
    while result.status == Status.INTERRUPTED:
        resumes += 1
        if resumes > 5:
            raise RuntimeError("too many resumes; something isn't converging")
        responses = [
            {"interruptResponse": {"interruptId": interrupt.id, "response": human_response}}
            for interrupt in result.interrupts
        ]
        result = await graph.invoke_async(responses, invocation_state=invocation_state)

    return {
        "status": str(result.status),
        "final_total": invocation_state.get("final_total"),
        "trace": invocation_state.get("final_trace"),
        "resumes": resumes,
    }


if __name__ == "__main__":
    for choice in ["add 2", "subtract 2"]:
        outcome = asyncio.run(run(choice))
        print(choice, "->", outcome)

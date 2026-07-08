import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from src.core.state import DebateState
from src.core.prompts import CON_OPENING, CON_REBUTTAL, CON_CLOSING, build_memory_block
from src.core.memory import retrieve_context

load_dotenv()

llm = ChatAnthropic(
    model=os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001"),
    streaming=True,
)


async def con_opening(state: DebateState) -> dict:
    context = retrieve_context(state["topic"])
    memory_block = build_memory_block(context)
    prompt = CON_OPENING.format(
        topic=state["topic"],
        pro_opening=state["pro_opening"],
        memory_block=memory_block,
    )
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    return {"con_opening": "".join(chunks), "memory_context": context}


async def con_rebuttal(state: DebateState) -> dict:
    memory_block = build_memory_block(state["memory_context"])
    prompt = CON_REBUTTAL.format(pro_opening=state["pro_opening"], memory_block=memory_block)
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    return {"con_rebuttal": "".join(chunks)}


async def con_closing(state: DebateState) -> dict:
    memory_block = build_memory_block(state["memory_context"])
    prompt = CON_CLOSING.format(memory_block=memory_block)
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    return {"con_closing": "".join(chunks)}

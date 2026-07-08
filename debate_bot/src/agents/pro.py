import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from src.core.state import DebateState
from src.core.prompts import PRO_OPENING, PRO_REBUTTAL, PRO_CLOSING, build_memory_block
from src.core.memory import retrieve_context

load_dotenv()

llm = ChatAnthropic(
    model=os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001"),
    streaming=True,
)


async def pro_opening(state: DebateState) -> dict:
    context = retrieve_context(state["topic"])
    memory_block = build_memory_block(context)
    prompt = PRO_OPENING.format(topic=state["topic"], memory_block=memory_block)
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    return {"pro_opening": "".join(chunks), "memory_context": context}


async def pro_rebuttal(state: DebateState) -> dict:
    memory_block = build_memory_block(state["memory_context"])
    prompt = PRO_REBUTTAL.format(con_opening=state["con_opening"], memory_block=memory_block)
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    return {"pro_rebuttal": "".join(chunks)}


async def pro_closing(state: DebateState) -> dict:
    memory_block = build_memory_block(state["memory_context"])
    prompt = PRO_CLOSING.format(memory_block=memory_block)
    chunks = []
    async for chunk in llm.astream(prompt):
        chunks.append(chunk.content)
    return {"pro_closing": "".join(chunks)}

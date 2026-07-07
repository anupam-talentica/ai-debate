import asyncio
import json
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from app import run_debate, graph, memory_store
from state import DebateState

# Pydantic models for request/response validation
class DebateRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="Debate topic")


class DebateResponse(BaseModel):
    topic: str
    round: str
    pro_opening: str
    con_opening: str
    pro_rebuttal: str
    con_rebuttal: str
    pro_closing: str
    con_closing: str
    moderator_summary: str
    winner: str
    memory_context: list


class HealthResponse(BaseModel):
    status: str = "healthy"
    message: str = "Debate bot is running"


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🤖 Debate Bot Server Starting...")
    yield
    # Shutdown
    print("👋 Debate Bot Server Shutting Down...")


# Create FastAPI app
app = FastAPI(
    title="Debate Bot API",
    description="Multi-agent debate orchestration with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for liveness probes."""
    return HealthResponse()


@app.post("/debate/invoke", response_model=DebateResponse, tags=["Debate"])
async def debate_invoke(request: DebateRequest) -> dict:
    """Run a full debate synchronously and return the complete final state."""
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    try:
        result = await run_debate(request.topic)
        return DebateResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debate execution failed: {str(e)}")


@app.get("/debate/stream", tags=["Debate"])
async def debate_stream(topic: str = Query(..., min_length=1, description="Debate topic")):
    """Stream debate execution as Server-Sent Events (SSE).

    Each SSE event represents a state update from the debate graph.
    Connect to this endpoint with an EventSource client to watch the debate unfold in real-time.
    """
    if not topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    async def event_generator():
        try:
            # Initialize the debate state
            initial_state: DebateState = {
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

            # Stream state updates from the graph
            async for state_update in graph.astream(initial_state):
                # Each state_update is (node_name, state_dict)
                if isinstance(state_update, tuple) and len(state_update) == 2:
                    node_name, state = state_update
                    # Send SSE event with the state update
                    event_data = {
                        "node": node_name,
                        "state": state,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    await asyncio.sleep(0.1)  # Small delay to prevent overwhelming client

            # Send completion event
            completion = {"node": "COMPLETE", "state": initial_state}
            yield f"data: {json.dumps(completion)}\n\n"

            # Upsert to memory after stream completes
            memory_store.upsert_debate(initial_state)

        except Exception as e:
            error_event = {"node": "ERROR", "error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

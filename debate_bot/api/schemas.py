from pydantic import BaseModel, Field


class DebateRequest(BaseModel):
    """Request model for starting a debate."""
    topic: str = Field(..., min_length=1, max_length=500, description="Debate topic")


class DebateResponse(BaseModel):
    """Response model for completed debate."""
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
    """Response model for health check."""
    status: str = "healthy"
    message: str = "Debate bot is running"


class DebateStreamEvent(BaseModel):
    """Response model for streaming debate events."""
    node: str = Field(..., description="Name of the graph node that executed")
    state: dict = Field(..., description="Current debate state after node execution")
    timestamp: float | None = Field(None, description="Unix timestamp of event")

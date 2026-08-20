from pydantic import BaseModel, Field, field_validator


class DebateRequest(BaseModel):
    """Request model for starting a debate."""
    topic: str = Field(..., min_length=1, max_length=500, description="Debate topic")

    @field_validator("topic")
    @classmethod
    def topic_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Topic cannot be empty or whitespace-only")
        return value


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


class DebateStartResponse(BaseModel):
    """Response model for starting a debate asynchronously."""
    run_id: str


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = "healthy"
    message: str = "Debate bot is running"
    node_id: str = Field(..., description="Identifies which node/container served this request")


class DebateStreamEvent(BaseModel):
    """Response model for streaming debate events."""
    node: str = Field(..., description="Name of the graph node that executed")
    state: dict = Field(..., description="Current debate state after node execution")
    timestamp: float | None = Field(None, description="Unix timestamp of event")

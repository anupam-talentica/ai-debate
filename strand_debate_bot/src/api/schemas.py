from pydantic import BaseModel, Field, field_validator


class DebateRequest(BaseModel):
    """Request model for starting or invoking a debate."""

    topic: str = Field(..., min_length=1, max_length=500, description="Debate topic")
    audience_question: str | None = Field(
        None,
        max_length=500,
        description="Optional audience question to pre-supply, so the run skips the post-rebuttal pause entirely.",
    )

    @field_validator("topic")
    @classmethod
    def topic_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Topic cannot be empty or whitespace-only")
        return value


class DebateResponse(BaseModel):
    """Response model for a completed debate."""

    topic: str
    round: str
    pro_opening: str
    con_opening: str
    pro_rebuttal: str
    con_rebuttal: str
    audience_question: str
    pro_audience_answer: str
    con_audience_answer: str
    pro_closing: str
    con_closing: str
    winner: str
    justification: str


class AudienceQuestionRequest(BaseModel):
    """Request model for submitting an audience question to a paused run."""

    question: str = Field(..., min_length=1, max_length=500, description="Audience question")

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be empty or whitespace-only")
        return value


class DebateStartResponse(BaseModel):
    """Response model for starting a debate asynchronously."""

    run_id: str


class HealthResponse(BaseModel):
    """Response model for the health check. No node_id -- single-process model,
    nothing to disambiguate (design.md, Context)."""

    status: str = "healthy"

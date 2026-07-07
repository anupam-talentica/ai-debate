import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.schemas import DebateRequest, DebateResponse, HealthResponse
from api.services.debate_service import DebateService
from api.services.exceptions import (
    DebateExecutionError,
    DebateTimeoutError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debate", tags=["Debate"])
debate_service = DebateService(timeout_seconds=60)


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for liveness probes."""
    logger.debug("Health check requested")
    return HealthResponse()


@router.post("/invoke", response_model=DebateResponse, tags=["Debate"])
async def debate_invoke(request: DebateRequest) -> dict:
    """
    Run a full debate synchronously and return the complete final state.

    Args:
        request: DebateRequest containing the debate topic

    Returns:
        DebateResponse with all debate arguments and winner

    Raises:
        HTTPException: 400 if topic is invalid, 500 if execution fails, 408 if timeout
    """
    logger.info(f"Debate invoked: {request.topic[:50]}...")

    try:
        result = await debate_service.execute_debate(request.topic)
        return DebateResponse(**result)

    except DebateTimeoutError as e:
        logger.warning(f"Debate timeout: {str(e)}")
        raise HTTPException(status_code=408, detail=str(e))

    except DebateExecutionError as e:
        logger.error(f"Debate execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error in debate_invoke: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected server error")


@router.get("/stream", tags=["Debate"])
async def debate_stream(topic: str = Query(..., min_length=1, max_length=500, description="Debate topic")):
    """
    Stream debate execution as Server-Sent Events (SSE).

    Each SSE event represents a state update from the debate graph.
    Connect to this endpoint with an EventSource client to watch the debate unfold in real-time.

    Args:
        topic: The debate topic

    Returns:
        StreamingResponse with SSE events
    """
    logger.info(f"Streaming debate: {topic[:50]}...")

    try:
        if not topic.strip():
            raise HTTPException(status_code=400, detail="Topic cannot be empty")

        return StreamingResponse(
            debate_service.stream_debate(topic),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    except DebateExecutionError as e:
        logger.error(f"Streaming error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error in debate_stream: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

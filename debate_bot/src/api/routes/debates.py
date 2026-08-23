import asyncio
import json
import logging
import uuid
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

import app as debate_app
from deployment.app_ext import event_bus, ownership
from src.api.schemas import (
    AudienceQuestionRequest,
    DebateRequest,
    DebateResponse,
    DebateStartResponse,
    HealthResponse,
)
from src.api.services.debate_service import DebateService
from src.api.services.exceptions import (
    DebateAwaitingInputError,
    DebateExecutionError,
    DebateTimeoutError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debate", tags=["Debate"])
debate_service = DebateService(timeout_seconds=60)


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint for liveness probes.

    Includes node_id in the response body so a load balancer's round-robin
    behavior is directly observable via repeated curls (see T4 test procedure).
    """
    logger.debug(f"Health check requested [node={debate_app.NODE_ID}]")
    return HealthResponse(node_id=debate_app.NODE_ID)


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
        result = await debate_service.execute_debate(request.topic, audience_question=request.audience_question)
        return DebateResponse(**result)

    except DebateTimeoutError as e:
        logger.warning(f"Debate timeout: {str(e)}")
        raise HTTPException(status_code=408, detail=str(e))

    except DebateAwaitingInputError as e:
        logger.warning(f"Debate awaiting audience question: {str(e)}")
        raise HTTPException(status_code=409, detail={"message": str(e), "run_id": e.run_id})

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


@router.post("/start", response_model=DebateStartResponse, tags=["Debate"])
async def debate_start(request: DebateRequest) -> dict:
    """
    Claim a fresh run_id on this node and start executing it in the background.

    The caller doesn't need to stay connected — any node can later serve
    `/debate/stream/{run_id}` by relaying events from Redis, or by claiming and
    resuming execution itself if this node's heartbeat goes stale.

    Args:
        request: DebateRequest containing the debate topic

    Returns:
        DebateStartResponse with the generated run_id
    """
    run_id = str(uuid.uuid4())
    logger.info(f"Starting debate [{run_id}] on {debate_app.NODE_ID}: {request.topic[:50]}...")

    await ownership.claim(run_id, debate_app.NODE_ID)
    asyncio.create_task(debate_service.run_and_publish(run_id, debate_app.NODE_ID, topic=request.topic))

    return {"run_id": run_id}


@router.post("/{run_id}/audience-question", tags=["Debate"])
async def submit_audience_question(run_id: str, request: AudienceQuestionRequest) -> dict:
    """
    Submit the single audience question for a debate paused after its rebuttal
    round, resuming its execution in the background.

    Args:
        run_id: The paused run's id, as returned by `POST /debate/start`
        request: AudienceQuestionRequest containing the question text

    Returns:
        Acknowledgement that the question was accepted and the run is resuming

    Raises:
        HTTPException: 404 if run_id is unknown, 409 if the run isn't
            currently awaiting a question (already answered, still running,
            or already done)
    """
    status = await ownership.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")
    if status != "waiting_for_input":
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is not awaiting an audience question (status={status})",
        )

    claimed = await ownership.claim(run_id, debate_app.NODE_ID)
    if not claimed:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id}'s audience question was already claimed by another request",
        )

    logger.info(f"Audience question submitted for [{run_id}] on {debate_app.NODE_ID}: {request.question[:50]}...")
    asyncio.create_task(debate_service.resume_with_answer(run_id, debate_app.NODE_ID, request.question))

    return {"run_id": run_id, "status": "resuming"}


# How often a relaying-only node re-checks whether the owner it's relaying
# for has gone stale, without waiting for the client to reconnect. Comfortably
# under ownership.STALE_AFTER_SECONDS so a stale owner is caught on the very
# next poll rather than sitting undetected for a whole staleness window.
RELAY_OWNERSHIP_POLL_SECONDS = 4.0


@router.get("/stream/{run_id}", tags=["Debate"])
async def debate_stream_relay(run_id: str):
    """
    Stream a run's events, relaying Redis pub/sub regardless of which node is
    executing it. If the current owner's heartbeat has gone stale (or the run
    is unowned), this node claims it and resumes execution itself from the
    last Postgres checkpoint — this is the automatic-failover path.

    This check isn't just made once at connection time: a relay-only node
    keeps re-checking every `RELAY_OWNERSHIP_POLL_SECONDS` for as long as the
    client stays connected. Otherwise a node that started out relaying for a
    live owner would never notice that owner die mid-stream, and the client's
    single long-lived SSE connection would sit there indefinitely — the
    stream looks alive but nothing is executing anymore.

    Args:
        run_id: The run to stream, as returned by `POST /debate/start`

    Returns:
        StreamingResponse with SSE events relayed from `debate:{run_id}`
    """
    # Subscribe before making the claim decision so no event published after
    # this point is ever missed, regardless of which branch below is taken.
    pubsub = await event_bus.open_subscription(run_id)

    async def event_source():
        try:
            if await ownership.is_owned_and_alive(run_id):
                logger.info(f"[{run_id}] owned and alive — {debate_app.NODE_ID} relaying only")
            elif await ownership.claim(run_id, debate_app.NODE_ID):
                logger.info(f"[{run_id}] stale/unowned — {debate_app.NODE_ID} claimed, resuming execution")
                asyncio.create_task(debate_service.run_and_publish(run_id, debate_app.NODE_ID, topic=None))
            else:
                logger.info(f"[{run_id}] lost claim race — {debate_app.NODE_ID} relaying only")

            async for event in event_bus.listen(pubsub, poll_timeout=RELAY_OWNERSHIP_POLL_SECONDS):
                if event is None:
                    # Quiet poll window — nothing published, but the client is
                    # still connected. Re-check the owner and self-claim if it
                    # went stale, so this same connection carries on relaying
                    # once a (possibly different) node resumes the run.
                    if not await ownership.is_owned_and_alive(run_id):
                        if await ownership.claim(run_id, debate_app.NODE_ID):
                            logger.info(
                                f"[{run_id}] owner went stale mid-stream — {debate_app.NODE_ID} claimed, resuming"
                            )
                            asyncio.create_task(
                                debate_service.run_and_publish(run_id, debate_app.NODE_ID, topic=None)
                            )
                        else:
                            logger.info(f"[{run_id}] lost mid-stream claim race — continuing to relay")
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            await event_bus.close_subscription(pubsub)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/resume/{run_id}", tags=["Debate"])
async def debate_resume(run_id: str):
    """
    Resume a previously-started debate from its last Postgres checkpoint, streamed
    as Server-Sent Events (SSE).

    Use this after a process restart (or any interruption) to continue a debate
    identified by the `run_id` returned in the `RUN_START` event of `/debate/stream`,
    rather than starting over.

    Args:
        run_id: Thread id of the run to resume

    Returns:
        StreamingResponse with SSE events
    """
    logger.info(f"Resuming debate: {run_id}")

    try:
        return StreamingResponse(
            debate_service.resume_debate(run_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    except DebateExecutionError as e:
        logger.error(f"Resume error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error in debate_resume: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

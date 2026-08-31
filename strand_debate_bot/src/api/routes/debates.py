import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.schemas import (
    AudienceQuestionRequest,
    DebateRequest,
    DebateResponse,
    DebateStartResponse,
    HealthResponse,
)
from src.api.services.debate_service import DebateService
from src.api.services.exceptions import DebateAwaitingInputError, DebateExecutionError, DebateTimeoutError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debate", tags=["Debate"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _service(request: Request) -> DebateService:
    return request.app.state.debate_service


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Liveness check. No node_id -- single-process model, nothing to
    disambiguate (design.md, Context)."""
    return HealthResponse()


@router.post("/invoke", response_model=DebateResponse, tags=["Debate"])
async def debate_invoke(request: DebateRequest, req: Request) -> dict:
    """Run a full debate synchronously and return the complete final state."""
    logger.info("Debate invoked: %s...", request.topic[:50])
    service = _service(req)

    try:
        result = await service.invoke(request.topic, audience_question=request.audience_question)
        return DebateResponse(**result)

    except DebateTimeoutError as exc:
        logger.warning("Debate timeout: %s", exc)
        raise HTTPException(status_code=408, detail=str(exc)) from exc

    except DebateAwaitingInputError as exc:
        logger.warning("Debate awaiting audience question: %s", exc)
        raise HTTPException(status_code=409, detail={"message": str(exc), "run_id": exc.run_id}) from exc

    except DebateExecutionError as exc:
        logger.error("Debate execution error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/stream", tags=["Debate"])
async def debate_stream(topic: str, req: Request) -> StreamingResponse:
    """Stream a fresh debate's execution as Server-Sent Events over this
    connection. If the run reaches the audience-question pause, an explicit
    event is emitted rather than resuming -- this endpoint has no resume
    machinery (design.md, Decision 3's "resumable=False" path)."""
    if not topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    logger.info("Streaming debate: %s...", topic[:50])
    service = _service(req)
    return StreamingResponse(service.stream_fresh(topic), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/start", response_model=DebateStartResponse, tags=["Debate"])
async def debate_start(request: DebateRequest, req: Request) -> dict:
    """Start a debate running in the background and return its run_id
    immediately, without requiring the caller to stay connected."""
    service = _service(req)
    run_id = service.start(request.topic, audience_question=request.audience_question)
    logger.info("Starting debate [%s]: %s...", run_id, request.topic[:50])
    return {"run_id": run_id}


@router.get("/stream/{run_id}", tags=["Debate"])
async def debate_stream_by_id(run_id: str, req: Request) -> StreamingResponse:
    """Stream a started run's events by id, whether it is still executing or
    already finished streaming its events into the queue."""
    service = _service(req)
    generator = service.stream_registered(run_id)
    if generator is None:
        raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")

    return StreamingResponse(generator, media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/resume/{run_id}", response_model=DebateStartResponse, tags=["Debate"])
async def debate_resume(run_id: str, req: Request) -> dict:
    """Resume a run by id after a process restart, continuing from its last
    durably-recorded point rather than restarting the debate."""
    service = _service(req)
    resumed_run_id = service.resume(run_id)

    if resumed_run_id is None:
        raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")

    logger.info("Resuming debate [%s]", run_id)
    return {"run_id": resumed_run_id}


@router.post("/{run_id}/audience-question", tags=["Debate"])
async def submit_audience_question(run_id: str, request: AudienceQuestionRequest, req: Request) -> dict:
    """Submit the audience question for a run paused after its rebuttal
    round, resuming its execution in the background."""
    service = _service(req)
    outcome = service.submit_audience_question(run_id, request.question)

    if outcome is None:
        raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")
    if outcome == "not_waiting":
        raise HTTPException(status_code=409, detail=f"Run {run_id} is not awaiting an audience question")

    logger.info("Audience question submitted for [%s]: %s...", run_id, request.question[:50])
    return {"run_id": run_id, "status": "resuming"}

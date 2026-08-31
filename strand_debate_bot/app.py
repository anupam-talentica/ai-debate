"""FastAPI application factory: wires the debate graph's dependencies (model,
memory store) once per process, and the API's run registry/service layer on
top of them (design.md, Context)."""

from fastapi import FastAPI
from strands.models.anthropic import AnthropicModel

from src.api.routes.agentcore import router as agentcore_router
from src.api.routes.debates import router as debate_router
from src.api.services.debate_service import DebateService
from src.api.services.run_registry import RunRegistry
from src.core.config import ANTHROPIC_API_KEY, MODEL_NAME, SESSION_STORAGE_DIRECTORY
from src.core.graph import build_graph, default_memory_store

INVOKE_TIMEOUT_SECONDS = 60.0


def _build_model() -> AnthropicModel:
    return AnthropicModel(
        client_args={"api_key": ANTHROPIC_API_KEY},
        model_id=MODEL_NAME,
        max_tokens=1024,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Debate Bot", version="1.0.0")

    model = _build_model()
    memory_store = default_memory_store()

    # A fresh Graph per run, sharing the same model/memory-store instances --
    # one Graph object cannot safely serve two concurrent debates (its
    # interrupt/execution state lives on `self`), but the model and memory
    # store underneath it are safe to share (debate_service.py, module docstring).
    # Keyed by run_id so each run's execution state and content are durable
    # across a process restart (debate-durability design.md, Decisions 1-2).
    def graph_factory(run_id: str):
        return build_graph(model=model, memory_store=memory_store, run_id=run_id)

    registry = RunRegistry()
    service = DebateService(
        graph_factory, registry, SESSION_STORAGE_DIRECTORY, timeout_seconds=INVOKE_TIMEOUT_SECONDS
    )

    app.state.debate_service = service
    app.include_router(debate_router)
    app.include_router(agentcore_router)

    return app


app = create_app()

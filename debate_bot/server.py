import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

import app as debate_app
from deployment.app_ext import event_bus, ownership
from src.api.routes.debates import router as debates_router

load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    logger.info(f"🤖 Debate Bot Server Starting... [node={debate_app.NODE_ID}]")
    await debate_app.init_checkpointer()
    logger.info("✓ Postgres checkpointer ready")
    await ownership.init_pool()
    logger.info("✓ Run ownership table ready")
    yield
    # Shutdown
    await debate_app.close_checkpointer()
    await ownership.close_pool()
    await event_bus.close()
    logger.info("👋 Debate Bot Server Shutting Down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Debate Bot API",
        description="Multi-agent debate orchestration with LangGraph",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Include routers
    app.include_router(debates_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

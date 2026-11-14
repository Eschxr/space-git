from contextlib import asynccontextmanager

from fastapi import FastAPI

from scene_tracker.core.logging import configure_logging
from scene_tracker.core.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(Settings().log_level)
    yield


app = FastAPI(title="Scene Tracker", version="0.1.0", lifespan=lifespan)


@app.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness only; does not claim dependency or model readiness."""
    return {"status": "ok"}

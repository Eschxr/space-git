import logging
from contextlib import asynccontextmanager
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from scene_tracker.api.limits import UploadLimitMiddleware
from scene_tracker.api.routes.captures import router
from scene_tracker.api.routes.highlights import router as highlights_router
from scene_tracker.api.routes.revisions import router as revisions_router
from scene_tracker.api.routes.tracks import router as tracks_router
from scene_tracker.core.errors import AppError
from scene_tracker.core.logging import configure_logging
from scene_tracker.core.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(app.state.settings.log_level)
    yield
    if engine := getattr(app.state, "engine", None):
        engine.dispose()


def create_app(settings=None, services=None):
    app = FastAPI(title="Scene Tracker", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.services = services
    app.state.services_lock = Lock()
    app.add_middleware(
        UploadLimitMiddleware, max_bytes=4 * app.state.settings.max_image_bytes + 65536
    )
    app.include_router(router)
    app.include_router(revisions_router)
    app.include_router(highlights_router)
    app.include_router(tracks_router)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, **exc.details}},
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        # Multipart parser errors (too many/duplicate camera file parts) are invalid captures.
        status = 422 if exc.status_code == 400 else exc.status_code
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": "invalid_capture" if status == 422 else "http_error",
                    "message": str(exc.detail),
                }
            },
        )

    @app.middleware("http")
    async def correlate(request: Request, call_next):
        correlation_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logging.getLogger(__name__).info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={"correlation_id": correlation_id},
        )
        return response

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

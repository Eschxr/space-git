from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from scene_tracker.api.dependencies import Services, get_services
from scene_tracker.api.schemas.captures import (
    CapturePage,
    CaptureResponse,
    DebugResponse,
    DetectionPage,
    EnvironmentCreate,
    EnvironmentResponse,
    ProcessRequest,
    RunResponse,
)
from scene_tracker.api.schemas.history import RunPage, WorkflowResponse
from scene_tracker.application.captures import CaptureService
from scene_tracker.application.ingest import ImageUpload
from scene_tracker.application.process import ProcessingService
from scene_tracker.application.workflow import capture_workflow, run_summary
from scene_tracker.core.errors import AppError
from scene_tracker.domain.enums import CameraID

router = APIRouter(prefix="/api/v1")
ServicesDep = Annotated[Services, Depends(get_services)]
ROLES = [c.value for c in CameraID]
TIMESTAMPS = [f"{c}_captured_at" for c in ROLES]
MULTIPART = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ROLES,
                    "properties": {
                        **{c: {"type": "string", "format": "binary"} for c in ROLES},
                        **{
                            c: {"type": "string", "format": "date-time"}
                            for c in ["captured_at", *TIMESTAMPS]
                        },
                    },
                }
            }
        },
    }
}


@router.post("/environments", response_model=EnvironmentResponse, status_code=201)
def create_environment(body: EnvironmentCreate, services: ServicesDep):
    return services.repository.create_environment(body.name, body.prompts)


@router.post(
    "/environments/{environment_id}/captures",
    response_model=CaptureResponse,
    status_code=201,
    openapi_extra=MULTIPART,
)
async def upload_capture(environment_id: UUID, request: Request, services: ServicesDep):
    async with request.form(
        max_files=4, max_fields=5, max_part_size=services.settings.max_image_bytes
    ) as form:
        keys = [key for key, _ in form.multi_items()]
        if (
            len(keys) != len(set(keys))
            or not set(ROLES).issubset(keys)
            or set(keys) - set(ROLES + TIMESTAMPS + ["captured_at"])
        ):
            raise AppError("invalid_capture", "Exactly four unique canonical files required", 422)
        timestamps = {}
        try:
            for name in ["captured_at", *TIMESTAMPS]:
                if name in form:
                    timestamps[name] = TypeAdapter(AwareDatetime).validate_python(form[name])
        except ValidationError as exc:
            raise AppError(
                "invalid_capture", "Timestamps must include timezone offsets", 422
            ) from exc
        uploads = []
        for camera in ROLES:
            value = form[camera]
            if not isinstance(value, UploadFile):
                raise AppError("invalid_capture", "Each camera role must be a file", 422)
            data = await value.read(services.settings.max_image_bytes + 1)
            uploads.append(
                ImageUpload(
                    CameraID(camera),
                    value.filename or "",
                    value.content_type or "",
                    data,
                    timestamps.get(f"{camera}_captured_at"),
                )
            )
        service = CaptureService(services.repository, services.store_factory, services.settings)
        return await run_in_threadpool(
            service.ingest,
            environment_id,
            timestamps.get("captured_at", datetime.now(UTC)),
            uploads,
        )


@router.get("/environments/{environment_id}/captures", response_model=CapturePage)
def list_captures(
    environment_id: UUID,
    services: ServicesDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return {
        "items": services.repository.list_captures(environment_id, limit, offset),
        "limit": limit,
        "offset": offset,
    }


@router.get("/captures/{capture_id}", response_model=CaptureResponse)
def get_capture(capture_id: UUID, services: ServicesDep):
    return services.repository.capture(capture_id)


@router.get("/captures/{capture_id}/processing-runs", response_model=RunPage)
def capture_runs(
    capture_id: UUID,
    services: ServicesDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = services.repository.list_runs(capture_id, limit, offset)
    with services.repository.engine.connect() as conn:
        items = [run_summary(conn, row) for row in rows]
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/captures/{capture_id}/workflow", response_model=WorkflowResponse)
def workflow(capture_id: UUID, services: ServicesDep):
    return capture_workflow(services, capture_id)


@router.post("/captures/{capture_id}/process", response_model=RunResponse, status_code=202)
def process(capture_id: UUID, body: ProcessRequest, services: ServicesDep):
    return ProcessingService(services.repository, services.dispatcher, services.settings).schedule(
        capture_id, body.preset, body.retry, body.reference_capture_id
    )


@router.get("/processing-runs/{run_id}", response_model=RunResponse)
def get_run(run_id: UUID, services: ServicesDep):
    return services.repository.run(run_id)


@router.get("/processing-runs/{run_id}/detections", response_model=DetectionPage)
def get_detections(
    run_id: UUID,
    services: ServicesDep,
    camera_id: CameraID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return {
        "items": services.repository.list_detections(run_id, camera_id, limit, offset),
        "limit": limit,
        "offset": offset,
    }


@router.get("/processing-runs/{run_id}/debug", response_model=DebugResponse)
def get_debug(run_id: UUID, services: ServicesDep):
    run = services.repository.run(run_id)
    store = services.store_factory(run["environment_id"])
    items = []
    for artifact in services.repository.list_artifacts(run_id):
        blob = store.stat(artifact["storage_key"])
        items.append(artifact | {"url": store.presign(blob), "trace_id": str(run_id)})
    return {"run_id": run_id, "manifest": run["model_manifest"], "artifacts": items}

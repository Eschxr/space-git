from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from scene_tracker.api.dependencies import Services, get_services
from scene_tracker.api.routes.captures import read_upload
from scene_tracker.application.camera_commits import CameraCommitService
from scene_tracker.core.errors import AppError

router = APIRouter(prefix="/api/v1/camera-commits")
ServicesDep = Annotated[Services, Depends(get_services)]


class CommitInput(BaseModel):
    source_session_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=2000)
    captured_at: AwareDatetime


@router.get("")
def list_commits(
    services: ServicesDep, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    return CameraCommitService(services).list(limit, offset)


@router.post("", status_code=201)
async def push_commit(request: Request, services: ServicesDep):
    _, uploads, fields = await read_upload(
        request, services, ("source_session_id", "message", "captured_at")
    )
    try:
        body = CommitInput.model_validate(fields)
    except ValidationError as error:
        raise AppError(
            "invalid_commit", "A saved session ID and commit message are required", 422
        ) from error
    if not body.message.strip():
        raise AppError("invalid_commit", "Enter a commit message", 422)
    return await run_in_threadpool(
        CameraCommitService(services).push,
        body.source_session_id,
        body.message,
        body.captured_at,
        uploads,
    )

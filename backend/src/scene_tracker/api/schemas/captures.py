from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from scene_tracker.domain.enums import CameraID, CaptureStatus, JobStatus


class EnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)


class EnvironmentResponse(BaseModel):
    id: UUID
    name: str
    created_at: AwareDatetime


class FrameResponse(BaseModel):
    id: UUID
    capture_id: UUID
    camera_id: CameraID
    role: Literal["side", "overhead"]
    storage_key: str
    sha256: str
    width: int
    height: int
    original_width: int
    original_height: int
    exif_orientation: int
    content_type: str
    captured_at: AwareDatetime | None


class CaptureSummary(BaseModel):
    id: UUID
    environment_id: UUID
    captured_at: AwareDatetime
    status: CaptureStatus
    source_manifest_hash: str | None
    warnings: list[str]
    error: str | None


class CaptureResponse(CaptureSummary):
    frames: list[FrameResponse]


class CapturePage(BaseModel):
    items: list[CaptureSummary]
    limit: int
    offset: int


class ProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset: Literal["skeleton"] = "skeleton"
    retry: bool = False


class JobResponse(BaseModel):
    id: UUID
    kind: Literal["vision", "reconstruction"]
    subject_id: UUID
    status: JobStatus
    idempotency_key: str
    run_id: UUID | None
    attempt: int
    error: str | None


class RunResponse(BaseModel):
    id: UUID
    capture_id: UUID
    status: JobStatus
    model_manifest: dict
    config_hash: str
    progress: dict
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    error: str | None
    job: JobResponse | None

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from scene_tracker.domain.enums import CameraID, CaptureStatus, JobStatus


class EnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    prompts: tuple[str, ...] | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def valid_prompts(self):
        if self.prompts and any(not p.strip() or len(p) > 80 or "." in p for p in self.prompts):
            raise ValueError("prompts must be nonempty phrases up to 80 characters without dots")
        return self


class EnvironmentResponse(BaseModel):
    prompts: list[str] | None = None
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
    preset: Literal["fake-fixture", "skeleton", "default"] = "fake-fixture"
    retry: bool = False
    reference_capture_id: UUID | None = None


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


class DetectionResponse(BaseModel):
    id: UUID
    run_id: UUID
    frame_id: UUID
    camera_id: CameraID
    label: str
    det_score: float
    box_xyxy: list[float]
    mask_key: str | None
    mask_score: float | None
    embedding_key: str | None
    embedding_metadata: dict | None
    debug_crop_key: str | None


class DetectionPage(BaseModel):
    items: list[DetectionResponse]
    limit: int
    offset: int


class DebugArtifact(BaseModel):
    id: UUID
    kind: str
    source_id: UUID
    camera_id: CameraID | None
    storage_key: str
    sha256: str
    content_type: str
    trace_id: str
    url: str


class DebugResponse(BaseModel):
    run_id: UUID
    manifest: dict
    artifacts: list[DebugArtifact]

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from scene_tracker.domain.enums import (
    CameraID,
    CaptureStatus,
    ChangeType,
    JobStatus,
    ReviewStatus,
    TrackStatus,
)

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Score = Annotated[float, Field(ge=0, le=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Frame(Contract):
    id: UUID
    capture_id: UUID
    camera_id: CameraID
    storage_key: str
    sha256: SHA256
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    original_width: int = Field(gt=0)
    original_height: int = Field(gt=0)
    exif_orientation: int = Field(ge=1, le=8, default=1)
    captured_at: AwareDatetime | None = None
    content_type: Literal["image/jpeg", "image/png", "image/webp"]

    @property
    def role(self) -> str:
        return self.camera_id.role


class Capture(Contract):
    id: UUID
    environment_id: UUID
    captured_at: AwareDatetime
    status: CaptureStatus
    frames: tuple[Frame, ...] = ()
    source_manifest_hash: SHA256 | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_roles(self):
        roles = [f.camera_id for f in self.frames]
        if len(set(roles)) != len(roles):
            raise ValueError("duplicate camera roles")
        if any(f.capture_id != self.id for f in self.frames):
            raise ValueError("frame belongs to another capture")
        if self.status == CaptureStatus.READY and set(roles) != set(CameraID):
            raise ValueError("ready capture requires exactly four camera roles")
        return self


class Mask(Contract):
    size: tuple[int, int]
    counts: str
    codec: Literal["coco_compressed_rle"] = "coco_compressed_rle"

    @model_validator(mode="after")
    def valid_size(self):
        if min(self.size) <= 0:
            raise ValueError("invalid mask dimensions")
        return self


class EmbeddingMetadata(Contract):
    storage_key: str
    dimension: int = Field(gt=0)
    dtype: Literal["float32"] = "float32"
    model: str
    sha256: SHA256
    normalized: bool = True


class Detection(Contract):
    id: UUID
    run_id: UUID
    frame_id: UUID
    camera_id: CameraID
    label: str
    det_score: Score
    box_xyxy: tuple[float, float, float, float]
    mask_key: str | None = None
    mask_score: Score | None = None
    embedding: EmbeddingMetadata | None = None

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.box_xyxy
        if not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError("expected oriented-frame pixel xyxy")
        return self


class ViewTrack(Contract):
    id: UUID
    environment_id: UUID
    camera_id: CameraID
    status: TrackStatus
    first_seen_at: AwareDatetime


class PhysicalObject(Contract):
    id: UUID
    environment_id: UUID
    label: str
    status: TrackStatus = TrackStatus.UNKNOWN


class ChangeProposal(Contract):
    id: UUID
    run_id: UUID
    object_id: UUID | None = None
    type: ChangeType
    status: ReviewStatus = ReviewStatus.PROPOSED
    evidence: dict = Field(default_factory=dict)
    before_ref: dict | None = None
    after_ref: dict | None = None
    reason: str | None = None


class Revision(Contract):
    id: UUID
    environment_id: UUID
    parent_id: UUID | None = None
    capture_id: UUID
    created_at: AwareDatetime
    message: str = ""


class Job(Contract):
    id: UUID
    kind: Literal["vision", "reconstruction"]
    subject_id: UUID
    status: JobStatus
    idempotency_key: str
    run_id: UUID | None = None
    attempt: int = Field(default=1, gt=0)
    error: str | None = None


class Artifact(Contract):
    id: UUID
    environment_id: UUID
    kind: str
    source_id: UUID
    camera_id: CameraID | None = None
    storage_key: str
    sha256: SHA256
    content_type: str


class ProcessingRun(Contract):
    id: UUID
    capture_id: UUID
    status: JobStatus
    config_hash: SHA256
    progress: dict = Field(default_factory=dict)
    model_manifest: dict = Field(default_factory=dict)
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    error: str | None = None


class TrackObservation(Contract):
    view_track_id: UUID
    detection_id: UUID
    capture_id: UUID
    match_score: Score
    match_metadata: dict = Field(default_factory=dict)


class ObjectTrackLink(Contract):
    physical_object_id: UUID
    view_track_id: UUID
    source: Literal["manual", "candidate"]
    review_status: ReviewStatus
    evidence: dict = Field(default_factory=dict)
    active: bool = True


class AssociationCandidate(Contract):
    id: UUID
    run_id: UUID
    kind: Literal["temporal", "cross_view"]
    source_id: UUID
    target_id: UUID
    features: dict = Field(default_factory=dict)
    score: Score
    decision: ReviewStatus = ReviewStatus.NEEDS_REVIEW


class Reconstruction(Contract):
    id: UUID
    capture_id: UUID
    revision_id: UUID | None = None
    status: JobStatus
    model_manifest: dict = Field(default_factory=dict)
    error: str | None = None

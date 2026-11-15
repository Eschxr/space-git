"""Browser-facing image history contracts, independent of worker/model libraries."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from scene_tracker.api.schemas.captures import CaptureResponse, FrameResponse
from scene_tracker.domain.enums import CameraID, JobStatus


class ReferenceSummary(BaseModel):
    kind: Literal["initial", "processed_run", "accepted_revision"]
    run_id: UUID | None = None
    capture_id: UUID | None = None
    revision_id: UUID | None = None
    inspection_reason: str | None = None


class RunSummary(BaseModel):
    id: UUID
    capture_id: UUID
    status: JobStatus
    config_hash: str
    job_id: UUID | None
    attempt: int | None
    scheduled_at: AwareDatetime | None = None
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    error: str | None
    provider: str | None
    inference_performed: bool
    reference: ReferenceSummary | None
    model_provenance: dict
    review_counts: dict[str, int]
    committed_revision_ids: list[UUID]


class RunPage(BaseModel):
    items: list[RunSummary]
    limit: int
    offset: int


class AssetEvidence(BaseModel):
    storage_key: str
    sha256: str | None = None
    content_type: str | None = None
    url: str | None = None
    unavailable_reason: str | None = None


class FrameEvidence(FrameResponse):
    image: AssetEvidence


class ObservationEvidence(BaseModel):
    capture_id: UUID
    frame_id: UUID
    camera_id: CameraID
    detection_id: UUID
    run_id: UUID | None
    label: str
    box_xyxy: list[float]
    width: int
    height: int
    orientation: Literal["canonical"] = "canonical"
    image: AssetEvidence
    mask: AssetEvidence | None
    crop: AssetEvidence | None
    overlays: list[AssetEvidence]


class TrackEvidence(BaseModel):
    view_track_id: UUID
    camera_id: CameraID
    state: dict
    observation: ObservationEvidence


class WorkflowResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    capture: CaptureResponse
    source_images: list[FrameEvidence]
    latest_run: RunSummary | None
    observed_tracks: list[TrackEvidence]
    approved_revision_id: UUID | None
    approved_evidence_path: str | None
    outcome: Literal[
        "unprocessed",
        "processing",
        "failed",
        "no_changes",
        "pending_review",
        "ready_to_commit",
        "review_complete",
        "committed",
        "inspection_only",
        "stale_baseline",
    ]


class ReviewDecision(BaseModel):
    id: UUID
    proposal_id: UUID
    previous_status: str
    new_status: Literal["accepted", "rejected", "needs_review"]
    previous_reason: str | None
    reason: str | None
    reviewer: str
    decided_at: AwareDatetime
    idempotency_key: str | None


class DecisionPage(BaseModel):
    proposal_id: UUID
    current_status: str
    current_reason: str | None
    items: list[ReviewDecision]
    limit: int
    offset: int


class RevisionMetadata(BaseModel):
    id: UUID
    environment_id: UUID
    parent_id: UUID | None
    capture_id: UUID
    created_at: AwareDatetime
    message: str
    idempotency_key: str | None
    request_hash: str | None


class RevisionResponse(RevisionMetadata):
    tracks: list[dict]
    evidence_path: str


class RevisionPage(BaseModel):
    items: list[RevisionMetadata]
    limit: int
    offset: int


class RevisionProvenance(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    origin: Literal["commit_snapshot", "derived_legacy"]
    capture_id: UUID
    run_ids: list[UUID]
    runs: list[dict]
    frames: list[dict]
    artifacts: list[dict]


class RevisionEvidence(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    revision: RevisionMetadata
    provenance: RevisionProvenance
    source_images: list[FrameEvidence]
    approved_tracks: list[TrackEvidence]
    changes: list[dict]
    highlight_paths: list[str]


class StateChange(BaseModel):
    view_track_id: UUID
    camera_id: CameraID
    kind: Literal["added", "removed", "missing", "restored", "changed", "unchanged"]
    fields: list[str]
    before: TrackEvidence | None
    after: TrackEvidence | None


class StateComparison(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    from_revision_id: UUID
    revision_id: UUID
    direction: Literal["identical", "forward", "reverse"]
    items: list[StateChange]


class AcceptedTrackEntry(BaseModel):
    revision: RevisionMetadata
    state: TrackEvidence
    before: TrackEvidence | None
    changes: list[dict]


class AcceptedTrackPage(BaseModel):
    view_track_id: UUID
    camera_id: CameraID
    environment_id: UUID
    items: list[AcceptedTrackEntry]
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

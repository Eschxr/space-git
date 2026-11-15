"""Canonical CPU-only contracts. Coordinates refer to EXIF-corrected RGB frames."""

from __future__ import annotations

import math
from typing import Literal, Protocol
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from scene_tracker.domain.contracts import Contract, Mask, Score
from scene_tracker.domain.enums import CameraID


class FrameContext(Contract):
    run_id: UUID
    frame_id: UUID
    camera_id: CameraID
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    trace_id: str
    coordinates: Literal["oriented_rgb_pixel_xyxy"] = "oriented_rgb_pixel_xyxy"


class DetectionBox(FrameContext):
    id: UUID
    fixture_id: str
    label: str
    score: Score
    box_xyxy: tuple[float, float, float, float]

    @model_validator(mode="after")
    def bounds(self):
        x1, y1, x2, y2 = self.box_xyxy
        if not (0 <= x1 < x2 <= self.width and 0 <= y1 < y2 <= self.height):
            raise ValueError("box outside oriented frame")
        return self


class InstanceMask(FrameContext):
    detection_id: UUID
    rle: Mask
    score: Score

    @model_validator(mode="after")
    def bounds(self):
        if self.rle.size != (self.height, self.width):
            raise ValueError("mask dimensions do not match frame")
        return self


class ObjectEmbedding(FrameContext):
    detection_id: UUID
    values: tuple[float, ...]
    dimension: int = Field(gt=0)
    dtype: Literal["float32"] = "float32"
    model: str = "fake-hash-v1"

    @model_validator(mode="after")
    def vector(self):
        if len(self.values) != self.dimension:
            raise ValueError("embedding dimension mismatch")
        if abs(math.sqrt(sum(v * v for v in self.values)) - 1) > 1e-5:
            raise ValueError("embedding must be L2 normalized")
        return self


class ArtifactRef(Contract):
    id: UUID
    key: str
    sha256: str
    content_type: str
    size: int
    camera_id: CameraID | None = None
    kind: str
    trace_id: str


class PerCameraResult(FrameContext):
    status: Literal["succeeded", "failed"]
    detections: tuple[DetectionBox, ...] = ()
    masks: tuple[InstanceMask, ...] = ()
    embeddings: tuple[ObjectEmbedding, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str | None = None


class ProcessingManifest(Contract):
    job_id: UUID | None = None
    attempt: int = Field(default=1, ge=1)
    scheduled_at: AwareDatetime | None = None
    reference: dict | None = None
    schema_version: Literal[1] = 1
    run_id: UUID
    capture_id: UUID
    trace_id: str
    provider: Literal["fake", "real"] = "fake"
    inference_performed: bool = False
    scope: Literal["synthetic_fixture_pipeline", "real_vision_pipeline"] = (
        "synthetic_fixture_pipeline"
    )
    config: dict
    config_hash: str
    provenance: dict
    sources: tuple[dict, ...]
    preprocessing: dict
    cameras: tuple[PerCameraResult, ...]
    artifacts: tuple[ArtifactRef, ...]
    timing_seconds: dict[str, float]
    errors: tuple[str, ...]


class Embedder(Protocol):
    def embed(self, rgb_image, instance_masks, boxes, config) -> list[ObjectEmbedding]: ...


class ObjectExtractor(Protocol):
    def extract(self, rgb_image, config) -> tuple[list[DetectionBox], list[InstanceMask]]: ...

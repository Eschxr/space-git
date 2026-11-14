"""Versioned CPU-only JSON contract shared by value with future reconstruction workers."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from scene_tracker.domain.contracts import Contract
from scene_tracker.domain.enums import CameraID

ChangeKind = Literal[
    "appeared_in_view",
    "moved_in_view",
    "appearance_changed",
    "missing_from_view",
    "reappeared",
    "uncertain",
]


class ImageSpace(Contract):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    orientation: Literal["canonical"] = "canonical"


class HighlightRegion(Contract):
    change_id: UUID
    view_track_id: UUID
    change_type: ChangeKind
    temporal_role: Literal["before", "after"]
    detection_id: UUID
    mask_ref: str | None
    mask_url: str | None = None
    unavailable_reason: str | None = None
    bbox_xyxy: tuple[float, float, float, float]
    highlight_rgb: tuple[int, int, int]

    @model_validator(mode="after")
    def valid(self):
        x1, y1, x2, y2 = self.bbox_xyxy
        if not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError("invalid highlight box")
        if any(not 0 <= v <= 255 for v in self.highlight_rgb):
            raise ValueError("invalid highlight color")
        if self.mask_ref is None and not self.unavailable_reason:
            raise ValueError("missing mask must have an explicit reason")
        return self


class HighlightManifest(Contract):
    schema_version: Literal["1.0"] = "1.0"
    capture_id: UUID
    camera_id: CameraID
    frame_id: UUID
    revision_id: UUID | None = None
    image: ImageSpace
    image_url: str | None = None
    regions: tuple[HighlightRegion, ...] = ()

    @model_validator(mode="after")
    def dimensions(self):
        for region in self.regions:
            if region.bbox_xyxy[2] > self.image.width or region.bbox_xyxy[3] > self.image.height:
                raise ValueError("highlight outside canonical image")
        return self

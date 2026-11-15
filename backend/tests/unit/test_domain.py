from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from scene_tracker.domain.contracts import Capture, Detection, EmbeddingMetadata, Mask
from scene_tracker.domain.enums import CameraID
from scene_tracker.infrastructure.db.models import metadata


def test_ready_capture_requires_four():
    with pytest.raises(ValidationError):
        Capture(id=uuid4(), environment_id=uuid4(), captured_at=datetime.now(UTC), status="ready")
    with pytest.raises(ValueError):
        CameraID("cam_05")


def test_canonical_vision_contracts():
    with pytest.raises(ValidationError):
        Mask(size=(0, 8), counts="abc")
    with pytest.raises(ValidationError):
        EmbeddingMetadata(storage_key="vector", dimension=0, model="fake", sha256="0" * 64)
    with pytest.raises(ValidationError):
        Detection(
            id=uuid4(),
            run_id=uuid4(),
            frame_id=uuid4(),
            camera_id="cam_01",
            label="chair",
            det_score=0.9,
            box_xyxy=(10, 0, 5, 2),
        )


def test_initial_schema_tables():
    assert len(metadata.tables) == 21
    assert metadata.tables["frames"].c.captured_at.type.timezone

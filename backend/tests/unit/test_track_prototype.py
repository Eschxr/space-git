"""Durable prototypes reference verified bytes; missing evidence cannot erase them."""

from copy import deepcopy
from uuid import uuid4

import numpy as np
import pytest

from scene_tracker.application.association import (
    appearance_prototype,
    previous_prototype,
    track_features,
    updated_prototype,
)
from scene_tracker.core.tracking_settings import TrackingSettings
from scene_tracker.infrastructure.storage.local import LocalStore


def observation(store):
    blob = store.put(
        f"vision/{uuid4()}/vector.f32",
        np.array([1, 0], dtype="<f4").tobytes(),
        "application/octet-stream",
    )
    return {
        "id": str(uuid4()),
        "frame_id": str(uuid4()),
        "capture_id": str(uuid4()),
        "camera_id": "cam_01",
        "label": "chair",
        "width": 64,
        "height": 64,
        "box_xyxy": [0, 0, 32, 32],
        "mask_key": None,
        "embedding_key": blob.key,
        "embedding_metadata": {"model": "stub", "dimension": 2, "sha256": blob.sha256},
    }


def test_prototype_retention_reload_and_legacy_compatibility(tmp_path):
    store = LocalStore(tmp_path, uuid4())
    obs = observation(store)
    old = {"view_track_id": str(uuid4()), "camera_id": "cam_01", "observation": obs}
    prototype = previous_prototype(old)
    assert prototype == appearance_prototype(obs)  # Legacy snapshot, no rewrite.
    missing = obs | {"id": str(uuid4()), "embedding_key": None, "embedding_metadata": {}}
    candidate = {"embedding_missing": True, "terms": {"appearance": None}}
    assert updated_prototype(old, missing, candidate, TrackingSettings()) == prototype
    current = old | {"observation": missing, "appearance_prototype": prototype}
    result = track_features(current, store)
    np.testing.assert_array_equal(result["feature"], [1, 0])
    assert result["appearance_reference"]["detection_id"] == obs["id"]
    before = deepcopy(current)
    other = observation(store)
    candidate = {"embedding_missing": False, "terms": {"appearance": 0.2}}
    assert updated_prototype(current, other, candidate, TrackingSettings()) == prototype
    candidate["terms"]["appearance"] = 0.95
    assert (
        updated_prototype(current, other, candidate, TrackingSettings())["detection_id"]
        == other["id"]
    )
    assert current == before
    assert updated_prototype(None, missing, None, TrackingSettings()) is None
    assert track_features(old | {"observation": missing}, store).get("feature") is None


def test_prototype_cannot_cross_camera_or_bypass_checksum(tmp_path):
    store = LocalStore(tmp_path, uuid4())
    obs = observation(store)
    prototype = appearance_prototype(obs)
    state = {
        "view_track_id": str(uuid4()),
        "camera_id": "cam_01",
        "observation": obs,
        "appearance_prototype": prototype | {"camera_id": "cam_02"},
    }
    with pytest.raises(ValueError, match="cross-camera"):
        track_features(state, store)
    prototype["embedding_metadata"] = prototype["embedding_metadata"] | {"sha256": "0" * 64}
    with pytest.raises(ValueError, match="checksum"):
        track_features(state | {"appearance_prototype": prototype}, store)

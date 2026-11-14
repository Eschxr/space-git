import numpy as np
import pytest

from scene_tracker.core.tracking_settings import TrackingSettings
from scene_tracker.vision.matching.intra_view import match


def obj(key, x=10, label="chair", camera="cam_01", seed=0):
    feature = np.zeros(8)
    feature[seed] = 1
    return {
        "id": key,
        "view_track_id": key,
        "camera_id": camera,
        "label": label,
        "box_xyxy": [x, 10, x + 20, 30],
        "width": 100,
        "height": 100,
        "feature": feature,
        "embedding_model": "fake",
    }


def test_stationary_moved_label_drift_and_camera_isolation():
    settings = TrackingSettings()
    for new in [obj("new"), obj("new", 60), obj("new", label="seat")]:
        result = match("cam_01", [obj("old")], [new], settings)
        assert result["matches"][0]["track_id"] == "old"
    with pytest.raises(ValueError, match="cross-camera"):
        match("cam_01", [obj("old", camera="cam_02")], [obj("new")], settings)


def test_close_identical_objects_uncertain_and_order_stable():
    settings = TrackingSettings()
    old = [obj("old-a"), obj("old-b", 11)]
    new = [obj("new-a", 10), obj("new-b", 11)]
    result = match("cam_01", old, new, settings)
    assert not result["matches"]
    assert len(result["uncertain_detections"]) == 2
    assert result == match("cam_01", list(reversed(old)), list(reversed(new)), settings)


def test_unmatched_and_distinct_assignment():
    settings = TrackingSettings()
    result = match(
        "cam_04",
        [obj("old-a", camera="cam_04"), obj("old-b", 60, camera="cam_04", seed=1)],
        [obj("new-a", camera="cam_04"), obj("new-b", 60, camera="cam_04", seed=1)],
        settings,
    )
    assert len(result["matches"]) == 2
    assert len({c["track_id"] for c in result["matches"]}) == 2
    assert not match("cam_01", [obj("old")], [], settings)["matches"]

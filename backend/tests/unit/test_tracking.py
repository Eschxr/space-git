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


def test_label_normalization_preserves_raw_glass_and_plural_boxes():
    from scene_tracker.vision.matching.costs import normalize_label

    assert normalize_label("  BOXES  ") == "box"
    assert normalize_label("Seats") == "chair"
    assert normalize_label("glass") == "glass"


def test_cost_components_scale_and_explicit_gate_reasons():
    from scene_tracker.vision.matching.costs import compare

    settings = TrackingSettings()
    stationary = compare(obj("old"), obj("new"), settings)
    moved = compare(obj("old"), obj("new", 60), settings)
    assert moved["valid"] and moved["terms"]["iou"] == 0
    assert moved["terms"]["appearance"] == 1
    assert moved["score"] > settings.minimum_score
    assert stationary["cost"] < moved["cost"]
    for candidate in (stationary, moved):
        assert sum(candidate["cost_components"].values()) == pytest.approx(candidate["cost"])
        assert candidate["cost"] == pytest.approx(1 - candidate["score"])
    oversized = obj("new") | {"box_xyxy": [0, 0, 90, 90]}
    gated = compare(obj("old"), oversized, settings)
    assert "area_ratio_exceeds_gate" in gated["gate_reasons"] and not gated["valid"]
    assert gated["terms"]["scale"] < 1
    unrelated = compare(obj("old"), obj("new", 60, seed=1), settings)
    assert "appearance_and_geometry_below_gates" in unrelated["gate_reasons"]
    missing = obj("new") | {"feature": None}
    fallback = compare(obj("old"), missing, settings)
    assert fallback["embedding_missing"]
    assert fallback["cost_components"]["missing_embedding_penalty"] > 0
    assert sum(fallback["cost_components"].values()) == pytest.approx(fallback["cost"])
    appearance_only = TrackingSettings(
        position_weight=0, iou_weight=0, class_weight=0, scale_weight=0
    )
    no_signal = compare(obj("old"), missing, appearance_only)
    assert not no_signal["valid"] and no_signal["score"] == 0
    assert sum(no_signal["cost_components"].values()) == 1


def test_screening_unmatched_reasons_and_duplicate_inputs():
    settings = TrackingSettings()
    report = match("cam_01", [obj("a"), obj("b", 11)], [obj("x"), obj("y", 11)], settings)
    assert all(
        r["ambiguous"] and len(r["top_two_scores"]) == 2 for r in report["screening"]["tracks"]
    )
    assert {r["reason"] for r in report["unmatched_tracks"]} == {"ambiguous"}
    assert all(c["reason_codes"] for c in report["candidates"])
    missing = match("cam_01", [obj("a")], [], settings)
    assert missing["unmatched_tracks"] == [{"id": "a", "reason": "no_candidates"}]
    gated = match("cam_01", [obj("a")], [obj("x", 60, seed=1)], settings)
    assert gated["unmatched_detections"] == [{"id": "x", "reason": "no_valid_candidates"}]
    boundary = match("cam_01", [obj("a")], [obj("x")], TrackingSettings(minimum_score=1))
    assert not boundary["matches"]
    assert boundary["unmatched_detections"][0]["reason"] == "below_threshold"
    for old, new in (([obj("a"), obj("a")], [obj("x")]), ([obj("a")], [obj("x"), obj("x")])):
        with pytest.raises(ValueError, match="duplicate"):
            match("cam_01", old, new, settings)


def test_dimension_normalization_and_single_assignment():
    a = obj("old")
    scaled = obj("new") | {"width": 200, "height": 200, "box_xyxy": [20, 20, 60, 60]}
    report = match("cam_01", [a], [scaled], TrackingSettings())
    assert report["matches"][0]["terms"]["displacement_norm"] == pytest.approx(0)
    assert report["matches"][0]["terms"]["scale"] == 1
    report = match("cam_01", [a], [obj("new"), obj("unrelated", 70, seed=1)], TrackingSettings())
    assert len(report["matches"]) == 1
    assert report["unmatched_detections"][0]["id"] == "unrelated"

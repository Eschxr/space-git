from uuid import uuid4

from scene_tracker.core.tracking_settings import TrackingSettings
from scene_tracker.vision.changes.propose import propose


def state():
    obs = {"box_xyxy": [0, 0, 32, 32], "width": 64, "height": 64}
    return {
        "view_track_id": str(uuid4()),
        "camera_id": "cam_01",
        "status": "observed",
        "observation": obs,
        "before": None,
        "match": None,
    }


def event(value):
    return [r["type"] for r in propose(uuid4(), [value], TrackingSettings())]


def test_initial_baseline_and_coarse_change_rules():
    s = state()
    assert event(s) == ["appeared_in_view"]
    s["before"] = s["observation"]
    s["match"] = {"score": 0.9, "terms": {"appearance": 0.99, "displacement_norm": 0.001}}
    assert event(s) == []  # Lighting/crop noise beneath configured tolerance.
    s["match"]["terms"]["displacement_norm"] = 0.2
    assert event(s) == ["moved_in_view"]
    s["uncertain"] = True
    assert event(s) == ["uncertain"]
    s["uncertain"] = False
    s["status"] = "unobserved"
    assert event(s) == ["missing_from_view"]
    s["status"] = "observed"
    s["before_missing_count"] = 1
    assert event(s) == ["reappeared"]
    s["before_missing_count"] = 0
    s["match"]["terms"] = {"appearance": 0.6, "displacement_norm": 0.001}
    assert event(s) == ["appearance_changed"]
    s["match"]["embedding_missing"] = True
    assert event(s) == ["uncertain"]


def test_historical_noncanonical_evidence_remains_readable():
    from types import SimpleNamespace

    from scene_tracker.api.routes.revisions import visualize

    legacy = {"type": "unobserved", "before_ref": {"position": [1, 2]}, "after_ref": None}
    services = SimpleNamespace(store_factory=lambda env: None)
    assert visualize(legacy, services, uuid4()) == legacy

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from scene_tracker.api.main import create_app
from scene_tracker.application.evidence import EvidenceReader
from scene_tracker.application.history import compare_states


def state():
    return {
        "view_track_id": str(uuid4()),
        "camera_id": "cam_01",
        "status": "observed",
        "uncertain": False,
        "observation": {
            "label": "chair",
            "width": 100,
            "height": 50,
            "box_xyxy": [0, 0, 10, 20],
            "mask_key": "old-mask",
            "embedding_metadata": {"sha256": "same-appearance"},
        },
    }


def test_endpoint_comparison_ignores_intermediate_runs_and_tracks_content():
    first = state()
    track = first["view_track_id"]
    later = deepcopy(first)
    later.update(run_id=str(uuid4()), capture_id=str(uuid4()), missing_count=9)
    later["observation"].update(mask_key="new-mask", width=200, height=100, box_xyxy=[0, 0, 20, 40])
    assert (
        compare_states({track: first}, {track: later}, lambda key: "same-mask")[0]["kind"]
        == "unchanged"
    )
    later["observation"]["embedding_metadata"]["sha256"] = "different"
    result = compare_states({track: first}, {track: later}, lambda key: "same-mask")[0]
    assert result["kind"] == "changed" and result["fields"] == ["appearance"]
    result = compare_states({track: first}, {track: later})[0]
    assert "mask" in result["fields"]
    assert compare_states({track: first}, {})[0]["kind"] == "removed"
    assert compare_states({}, {track: first})[0]["kind"] == "added"
    later["status"] = "unobserved"
    assert compare_states({track: first}, {track: later})[0]["kind"] == "missing"
    assert compare_states({track: later}, {track: first})[0]["kind"] == "restored"
    assert first["status"] == "observed"


def test_unavailable_blob_retains_reference_and_hash():
    class MissingStore:
        def stat(self, key):
            raise FileNotFoundError(key)

    reader = EvidenceReader(SimpleNamespace(store_factory=lambda env: MissingStore()), uuid4())
    evidence = reader.asset("vision/run/image.png", "a" * 64, "image/png")
    assert evidence == {
        "storage_key": "vision/run/image.png",
        "sha256": "a" * 64,
        "content_type": "image/png",
        "url": None,
        "unavailable_reason": "missing_blob",
    }


def test_image_history_openapi_keeps_event_and_observation_endpoints():
    schema = create_app().openapi()
    routes = {
        "/api/v1/captures/{capture_id}/workflow": "WorkflowResponse",
        "/api/v1/captures/{capture_id}/processing-runs": "RunPage",
        "/api/v1/change-proposals/{proposal_id}/decisions": "DecisionPage",
        "/api/v1/revisions/{revision_id}/evidence": "RevisionEvidence",
        "/api/v1/revisions/{revision_id}/compare": "StateComparison",
        "/api/v1/view-tracks/{track_id}/revisions": "AcceptedTrackPage",
    }
    for path, model in routes.items():
        response = schema["paths"][path]["get"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"]["$ref"].endswith("/" + model)
    assert "/api/v1/revisions/{revision_id}/diff" in schema["paths"]
    assert "/api/v1/view-tracks/{track_id}/history" in schema["paths"]

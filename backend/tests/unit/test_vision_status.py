from fastapi.testclient import TestClient

from scene_tracker.api.main import create_app
from scene_tracker.core.settings import Settings


def test_fake_status_is_explicit_and_does_not_preflight(monkeypatch):
    def forbidden(*args):
        raise AssertionError("fake mode must not verify pretrained assets")

    monkeypatch.setattr("scene_tracker.api.routes.vision.preflight", forbidden)
    client = TestClient(create_app(Settings(_env_file=None, vision_provider="fake")))
    result = client.get("/api/v1/vision/status").json()
    assert result["provider"] == "fake"
    assert result["assets_verified"] is False
    assert result["reason"] is None


def test_missing_real_assets_report_unavailable_without_fallback():
    client = TestClient(create_app(Settings(_env_file=None, vision_provider="real")))
    response = client.get("/api/v1/vision/status")
    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "real"
    assert result["assets_verified"] is False
    assert "missing" in result["reason"]


def test_verified_files_do_not_claim_worker_runtime_readiness(monkeypatch):
    monkeypatch.setattr("scene_tracker.api.routes.vision.preflight", lambda _: {})
    client = TestClient(create_app(Settings(_env_file=None, vision_provider="real")))
    result = client.get("/api/v1/vision/status").json()
    assert result["assets_verified"] is True
    assert result["detector"] == "YOLOE 11s prompt-free"
    assert result["embedder"] == "DINOv2 ViT-S/14"
    assert "ready" not in result

from fastapi.testclient import TestClient

from scene_tracker.api.main import app


def test_live():
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

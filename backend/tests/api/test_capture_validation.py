from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from scene_tracker.api.main import create_app
from scene_tracker.core.settings import Settings


def client():
    settings = Settings(_env_file=None)
    services = SimpleNamespace(settings=settings)
    return TestClient(create_app(settings, services))


@pytest.mark.parametrize(
    "roles",
    [
        ["cam_01", "cam_02", "cam_03"],
        ["cam_01", "cam_02", "cam_03", "cam_01"],
        ["cam_01", "cam_02", "cam_03", "cam_04", "cam_04"],
        ["cam_01", "cam_02", "cam_03", "cam_05"],
    ],
)
def test_missing_duplicate_unknown_camera(roles):
    response = client().post(
        f"/api/v1/environments/{uuid4()}/captures",
        files=[(c, (f"{c}.png", b"x", "image/png")) for c in roles],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_capture"


def test_invalid_timestamp_and_openapi():
    api = client()
    response = api.post(
        f"/api/v1/environments/{uuid4()}/captures",
        files=[
            (c, (f"{c}.png", b"x", "image/png")) for c in ["cam_01", "cam_02", "cam_03", "cam_04"]
        ],
        data={"captured_at": "2026-01-01T12:00:00"},
    )
    assert response.status_code == 422
    schema = api.get("/openapi.json").json()
    upload = schema["paths"]["/api/v1/environments/{environment_id}/captures"]["post"]
    roles = upload["requestBody"]["content"]["multipart/form-data"]["schema"]["required"]
    assert roles == ["cam_01", "cam_02", "cam_03", "cam_04"]


def test_extra_process_fields_rejected():
    response = client().post(
        f"/api/v1/captures/{uuid4()}/process", json={"preset": "skeleton", "path": "/tmp/image"}
    )
    assert response.status_code == 422


def test_total_request_size_limit():
    settings = Settings(_env_file=None, max_image_bytes=1)
    api = TestClient(create_app(settings, SimpleNamespace(settings=settings)))
    response = api.post(
        f"/api/v1/environments/{uuid4()}/captures",
        content=b"x" * 70000,
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert response.status_code == 413

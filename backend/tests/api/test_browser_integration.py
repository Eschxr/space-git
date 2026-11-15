from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from scene_tracker.api.main import create_app
from scene_tracker.core.settings import Settings


def test_environment_picker_pagination_and_contract():
    item = {"id": uuid4(), "name": "Lab", "created_at": datetime.now(UTC), "prompts": None}
    calls = []

    def list_environments(limit, offset):
        calls.append((limit, offset))
        return [item]

    services = SimpleNamespace(repository=SimpleNamespace(list_environments=list_environments))
    client = TestClient(create_app(Settings(_env_file=None), services))
    response = client.get("/api/v1/environments?limit=1&offset=2")
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            item
            | {
                "id": str(item["id"]),
                "created_at": item["created_at"].isoformat().replace("+00:00", "Z"),
            }
        ],
        "limit": 1,
        "offset": 2,
    }
    assert calls == [(1, 2)]
    assert client.get("/api/v1/environments?limit=101").status_code == 422
    assert client.get("/api/v1/environments?offset=-1").status_code == 422


def test_cors_preflight_and_error_response_are_limited_to_configured_frontend():
    client = TestClient(create_app(Settings(_env_file=None)))
    headers = {
        "Origin": "http://127.0.0.1:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/api/v1/environments", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]
    invalid = client.post("/api/v1/environments", json={"name": ""}, headers=headers)
    assert invalid.status_code == 422
    assert invalid.headers["access-control-allow-origin"] == headers["Origin"]
    denied = client.options(
        "/api/v1/environments", headers=headers | {"Origin": "https://untrusted.example"}
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers

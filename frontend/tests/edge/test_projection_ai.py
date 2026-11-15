"""Offline Ollama protocol/validation tests. No model downloads or real inference."""
import json
from io import BytesIO
from urllib.error import URLError

from fastapi.testclient import TestClient
import pytest

from spacegit_edge.main import make_app
from spacegit_edge import projection_ai as ai

TOKEN = "projection-test-only-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
OBJECT = {"id": "sphere-1", "name": "Blue orb", "shape": "sphere", "color": "#72d5ef",
          "animation": "float", "position": [0, 0, 0], "size": 0.18}


@pytest.fixture
def client(tmp_path):
    with TestClient(make_app(path=tmp_path / "db.sqlite", mode="demo", token=TOKEN)) as result:
        yield result


def test_authenticated_installed_models_and_validated_chat(client, monkeypatch):
    calls = []

    def transport(request, timeout):
        calls.append((request.full_url, timeout))
        if request.full_url.endswith("/api/tags"):
            return BytesIO(json.dumps({"models": [{"name": "local-test:latest"}]}).encode())
        body = json.loads(request.data)
        assert body["stream"] is False
        assert body["model"] == "local-test:latest"
        assert body["format"]["additionalProperties"] is False
        assert body["format"]["properties"]["objects"]["maxItems"] == 12
        assert json.loads(body["messages"][-1]["content"])["current_objects"] == []
        assert body["messages"][1] == {"role": "user", "content": "Earlier context"}
        return BytesIO(json.dumps({"done": True, "message": {"content": json.dumps({
            "reply": "Added a floating blue orb.", "objects": [OBJECT]})}}).encode())

    monkeypatch.setattr(ai, "urlopen", transport)
    assert client.get("/api/v1/projection/models").status_code == 401
    assert client.post("/api/v1/projection/chat", json={}).status_code == 401
    assert client.get("/api/v1/projection/models", headers=AUTH).json()["models"] == ["local-test:latest"]
    response = client.post("/api/v1/projection/chat", headers=AUTH, json={"model": "local-test:latest",
        "prompt": "Add a floating blue sphere", "objects": [],
        "messages": [{"role": "user", "content": "Earlier context"}]})
    assert response.status_code == 200
    assert response.json()["objects"] == [OBJECT]
    assert response.json()["provider"] == "ollama"
    assert all(url.endswith(("/api/tags", "/api/chat")) for url, _ in calls)
    assert calls[-1][1] == 120


@pytest.mark.parametrize("bad", [
    {**OBJECT, "shape": "javascript"}, {**OBJECT, "position": [2, 0, 0]},
    {**OBJECT, "position": [0, 0]}, {**OBJECT, "size": 0}, {**OBJECT, "color": "url(script)"},
    {**OBJECT, "script": "bad()"},
])
def test_invalid_model_output_never_applies_edits(client, monkeypatch, bad):
    monkeypatch.setattr(ai, "installed_models", lambda: ["test"])
    monkeypatch.setattr(ai, "ollama", lambda *args, **kwargs: {"done": True, "message": {
        "content": json.dumps({"reply": "Changed", "objects": [bad]})}})
    result = client.post("/api/v1/projection/chat", headers=AUTH,
                         json={"model": "test", "prompt": "Change it", "objects": [OBJECT]})
    assert result.status_code == 502
    assert "No scene edits" in result.json()["detail"]
    assert "objects" not in result.json()


def test_unavailable_unknown_incomplete_and_duplicate_plans(client, monkeypatch):
    def offline(*args, **kwargs):
        raise URLError("offline")
    monkeypatch.setattr(ai, "urlopen", offline)
    assert client.get("/api/v1/projection/models", headers=AUTH).status_code == 503
    payload = {"model": "missing", "prompt": "Add a sphere", "objects": []}
    assert client.post("/api/v1/projection/chat", headers=AUTH, json=payload).status_code == 503
    monkeypatch.setattr(ai, "installed_models", lambda: ["test"])
    assert client.post("/api/v1/projection/chat", headers=AUTH, json=payload).status_code == 409
    payload["model"] = "test"
    for result in ({"done": False}, {"done": True, "message": {"content": "bad json"}},
                   {"done": True, "message": {"content": json.dumps({"reply": "Duplicate", "objects": [OBJECT, OBJECT]})}}):
        monkeypatch.setattr(ai, "ollama", lambda *args, result=result, **kwargs: result)
        assert client.post("/api/v1/projection/chat", headers=AUTH, json=payload).status_code == 502
    payload["objects"] = [OBJECT, OBJECT]
    assert client.post("/api/v1/projection/chat", headers=AUTH, json=payload).status_code == 422

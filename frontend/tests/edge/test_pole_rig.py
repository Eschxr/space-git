import time

from fastapi.testclient import TestClient
import pytest

from spacegit_edge.main import make_app
from spacegit_edge.rig import camera_mapping

TOKEN = "pole-test-only-operator-token-2026"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_mapping_checks_physical_slot_order():
    assert camera_mapping("primary,2,-,0") == {1: "primary", 2: 2, 3: None, 4: 0}
    for raw in ("primary,primary,-,-", "0,00,-,-", "0,1,2,16", "0,1,2"):
        with pytest.raises(ValueError):
            camera_mapping(raw)


def test_rig_persists_fresh_frames_independently(tmp_path, monkeypatch):
    monkeypatch.setenv("SPACEGIT_RIG_CAMERAS", "primary,1,-,3")
    app = make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)
    with TestClient(app) as client:
        assert client.get("/api/v1/rig").status_code == 401
        assert client.get("/api/v1/rig",headers={**AUTH,"Origin":"https://example.org"}).status_code == 403
        assert client.post("/api/v1/rig/captures",headers=AUTH).status_code == 409
        state = app.state.runtime
        state.pole.enabled = True
        state.camera.latest = (time.time(), {}, b"radial A")
        state.pole.cameras[1].latest = (time.time()-3, {}, b"stale")
        state.pole.cameras[3].latest = (time.time(), {}, b"floor")
        before = client.get("/api/v1/commits",headers=AUTH).json()
        assert [feed["status"] for feed in client.get("/api/v1/rig",headers=AUTH).json()["feeds"]] == ["live","offline","unmapped","live"]
        stored = client.post("/api/v1/rig/captures",headers=AUTH)
        assert stored.status_code == 201
        capture = stored.json()
        assert capture["mode"] == "live" and capture["feeds"] == [1,4]
        assert capture["head"] == before["branches"]["main"]
        assert client.get("/api/v1/rig/captures",headers=AUTH).json()[0]["id"] == capture["id"]
        assert client.get(f"/api/v1/rig/captures/{capture['id']}/frames/4",headers=AUTH).content == b"floor"
        assert client.get(f"/api/v1/rig/captures/{capture['id']}/frames/2",headers=AUTH).status_code == 404
        assert client.get("/api/v1/commits",headers=AUTH).json() == before


def test_sequence_changes_keep_active_devices_and_old_captures(tmp_path, monkeypatch):
    monkeypatch.setenv("SPACEGIT_RIG_CAMERAS", "0,-,-,1")
    app = make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)
    path = "/api/v1/rig"
    with TestClient(app) as client:
        rig = app.state.runtime.pole
        first = rig.cameras[0]
        rig.enabled = True
        first.latest = (time.time(), {}, b"first device")
        rig.cameras[1].latest = (time.time(), {}, b"second device")
        capture = client.post(path + "/captures", headers=AUTH).json()
        assert capture["order"] == [1, 2, 3, 4]
        settings = {"sources": [1, None, None, 0], "order": [4, 1, 2, 3]}
        assert client.post(path + "/settings", headers=AUTH, json=settings).json()["settings"] == settings
        assert rig.cameras[0] is first
        assert client.get(path + "/frames/4", headers=AUTH).content == b"first device"
        assert client.get(path + f"/captures/{capture['id']}/frames/4", headers=AUTH).content == b"second device"
        assert client.post(path + "/captures", headers=AUTH).json()["feeds"] == [4, 1]
        for invalid in (dict(settings, sources=[0, 0, None, None]), dict(settings, order=[4, 4, 2, 3])):
            assert client.post(path + "/settings", headers=AUTH, json=invalid).status_code == 422
        assert client.get(path, headers=AUTH).json()["settings"] == settings
    with TestClient(app) as client:
        assert client.get(path, headers=AUTH).json()["settings"] == settings


def test_capture_can_connect_via_a_loopback_session(tmp_path, monkeypatch):
    monkeypatch.setenv("SPACEGIT_LOCAL_SESSION", "1")
    app = make_app(path=tmp_path / "db.sqlite", mode="demo", token=TOKEN)
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 15000)) as client:
        path = "/api/v1/local-session"
        origin = "http://127.0.0.1:3000"
        headers = {"Origin": origin, "X-SpaceGit-Local": "1"}
        assert client.post(path, headers={"Origin": origin}).status_code == 403
        assert client.post(path, headers={**headers, "X-Forwarded-For": "127.0.0.1"}).status_code == 403
        assert client.post(path, headers={**headers, "Origin": "https://example.org"}).status_code == 403
        session = client.post(path, headers=headers).json()["token"]
        auth = {"Authorization": f"Bearer {session}"}
        assert client.get("/api/v1/rig", headers={**auth, "Origin": origin}).status_code == 200
        assert client.get("/api/v1/rig", headers={**auth, "Origin": "http://localhost:3000"}).status_code == 401


def test_demo_never_opens_or_claims_live_cameras(tmp_path):
    with TestClient(make_app(path=tmp_path / "db.sqlite", mode="demo", token=TOKEN)) as client:
        assert {item["status"] for item in client.get("/api/v1/rig",headers=AUTH).json()["feeds"]} == {"simulated"}
        assert client.post("/api/v1/rig/start",headers=AUTH).status_code == 409
        assert client.post("/api/v1/rig/captures",headers=AUTH).status_code == 409

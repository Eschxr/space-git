import hashlib
import time

from fastapi.testclient import TestClient
import pytest

from spacegit_edge.main import make_app
from spacegit_edge.rig import camera_mapping
from spacegit_edge.rig import EXPORT_NAMES, export_frames
from spacegit_edge import rig as rig_module

TOKEN = "pole-test-only-operator-token-2026"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_pointcloud_downloads_use_capture_roles_and_require_authorization(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(rig_module, "POINTDIT_OUTPUT", output)
    for slot, name in EXPORT_NAMES.items():
        (output / (rig_module.Path(name).stem + "_pointcloud.ply")).write_bytes(b"ply\n" + bytes([slot]))
    app = make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)
    with TestClient(app) as client:
        assert client.get("/api/v1/rig/pointclouds/4").status_code == 401
        for slot in (4, 1, 2, 3):
            result = client.get(f"/api/v1/rig/pointclouds/{slot}", headers=AUTH)
            assert result.status_code == 200
            assert result.content == b"ply\n" + bytes([slot])
            assert result.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/rig/pointclouds/5", headers=AUTH).status_code == 404
        (output / "04_floor_pointcloud.ply").unlink()
        assert client.get("/api/v1/rig/pointclouds/4", headers=AUTH).status_code == 404


@pytest.mark.parametrize("fails", [False, True])
def test_four_camera_capture_exports_before_generating_ply(tmp_path, monkeypatch, fails):
    monkeypatch.setenv("SPACEGIT_POINTDIT_WSL", "1")
    monkeypatch.setenv("SPACEGIT_CAPTURE_EXPORT_DIR", r"\\wsl.localhost\Ubuntu\home\wilson\test_images")
    monkeypatch.setenv("SPACEGIT_RIG_CAMERAS", "0,1,2,3")
    calls = []

    def export(directory, frames):
        assert set(frames) == {1, 2, 3, 4}
        calls.append("export")

    def generate(log):
        assert calls == ["export"]
        calls.append("generate")
        if fails:
            raise RuntimeError("model failed")
        paths = [tmp_path / rig_module.cloud_name(slot) for slot in (1, 2, 3, 4)]
        for slot, path in enumerate(paths, 1):
            path.write_bytes(b"ply\n" + bytes([slot]))
        return [str(path) for path in paths]

    monkeypatch.setattr(rig_module, "export_frames", export)
    monkeypatch.setattr(rig_module, "generate_pointdit", generate)
    app = make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)
    with TestClient(app) as client:
        pole = app.state.runtime.pole
        pole.enabled = True
        for index in range(3):
            pole.cameras[index].latest = (time.time(), {}, b"jpeg")
        assert client.post("/api/v1/rig/captures", headers=AUTH).status_code == 409
        assert calls == []
        pole.cameras[3].latest = (time.time(), {}, b"floor")
        result = client.post("/api/v1/rig/captures", headers=AUTH)
        assert result.status_code == (503 if fails else 201)
        assert calls == ["export", "generate"]
        saved = client.get("/api/v1/rig/captures", headers=AUTH).json()[0]
        assert saved["pointdit"]["status"] == ("failed" if fails else "succeeded")
        if not fails:
            assert len(saved["pointdit"]["files"]) == 4
            assert saved["pointdit"]["model_id"] == saved["id"]
            versions = client.get("/api/v1/rig/models", headers=AUTH).json()
            assert [item["capture_id"] for item in versions] == [saved["id"]]
            (tmp_path / rig_module.cloud_name(4)).write_bytes(b"ply\nnew floor")
            archived = client.get(f"/api/v1/rig/models/{saved['id']}/pointclouds/4", headers=AUTH)
            assert archived.content == b"ply\n\x04"
        else:
            assert client.get("/api/v1/rig/models", headers=AUTH).json() == []


def test_archive_current_keeps_independent_versions_and_rejects_partial_sets(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(rig_module, "POINTDIT_OUTPUT", output)
    floors = [b"ply\nfirst floor", b"ply\nsecond floor"]
    with TestClient(make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)) as client:
        assert client.post("/api/v1/rig/models/import-current", headers=AUTH).status_code == 404
        assert client.get("/api/v1/rig/models").status_code == 401
        for slot in (1, 2, 3):
            (output / rig_module.cloud_name(slot)).write_bytes(b"ply\n" + bytes([slot]))
        ids = []
        for floor in floors:
            (output / rig_module.cloud_name(4)).write_bytes(floor)
            response = client.post("/api/v1/rig/models/import-current", headers=AUTH)
            assert response.status_code == 201
            model = response.json()
            assert model["capture_id"] is None
            assert model["files"][3]["sha256"] == hashlib.sha256(floor).hexdigest()
            ids.append(model["id"])
        assert ids[0] != ids[1]
        assert client.post("/api/v1/rig/models/import-current", headers=AUTH).json()["id"] == ids[1]
        (output / rig_module.cloud_name(1)).unlink()
        assert client.post("/api/v1/rig/models/import-current", headers=AUTH).status_code == 404
        assert {model["id"] for model in client.get("/api/v1/rig/models", headers=AUTH).json()} == set(ids)
    with TestClient(make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)) as client:
        for ident, floor in zip(ids, floors):
            assert client.get(f"/api/v1/rig/models/{ident}/pointclouds/4", headers=AUTH).content == floor


def test_pointdit_checks_fresh_output_and_activates_wsl_environment(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(rig_module, "POINTDIT_OUTPUT", output)

    def run(command, **kwargs):
        assert command[:7] == ["wsl.exe", "-d", "Ubuntu", "-u", "wilson", "--", "bash"]
        assert "source .venv/bin/activate" in command[-1]
        assert "bash scripts/demo_l_512.sh" in command[-1]
        for name in EXPORT_NAMES.values():
            (output / (rig_module.Path(name).stem + "_pointcloud.ply")).write_bytes(b"ply\nend_header\n")
        return rig_module.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(rig_module.subprocess, "run", run)
    assert len(rig_module.generate_pointdit(tmp_path / "run.log")) == 4
    monkeypatch.setattr(rig_module.subprocess, "run", lambda *args, **kwargs: rig_module.subprocess.CompletedProcess(args, 0))
    with pytest.raises(RuntimeError, match="did not update"):
        rig_module.generate_pointdit(tmp_path / "stale.log")


def test_capture_exports_named_frames_and_replaces_previous_contents(tmp_path, monkeypatch):
    destination = tmp_path / "test_images"
    destination.mkdir()
    (destination / "old.jpg").write_bytes(b"old image")
    monkeypatch.setenv("SPACEGIT_CAPTURE_EXPORT_DIR", str(destination))
    monkeypatch.setenv("SPACEGIT_RIG_CAMERAS", "0,1,2,3")
    app = make_app(path=tmp_path / "db.sqlite", mode="live", token=TOKEN)
    with TestClient(app) as client:
        pole = app.state.runtime.pole
        pole.enabled = True
        pole.settings = pole.settings.model_copy(update={"order": (4, 3, 2, 1)})
        for slot in (1, 2, 3, 4):
            pole.cameras[slot - 1].latest = (time.time(), {}, bytes([slot]))
        first = client.post("/api/v1/rig/captures", headers=AUTH)
        assert first.status_code == 201
        assert sorted(path.name for path in destination.iterdir()) == list(EXPORT_NAMES.values())
        for slot, name in EXPORT_NAMES.items():
            assert (destination / name).read_bytes() == bytes([slot])
        pole.cameras[0].latest = (time.time(), {}, b"new A")
        for index in (1, 2, 3):
            pole.cameras[index].latest = None
        assert client.post("/api/v1/rig/captures", headers=AUTH).status_code == 201
        assert [path.name for path in destination.iterdir()] == [EXPORT_NAMES[1]]
        assert (destination / EXPORT_NAMES[1]).read_bytes() == b"new A"
        ident = first.json()["id"]
        assert client.get(f"/api/v1/rig/captures/{ident}/frames/4", headers=AUTH).content == b"\x04"


def test_export_failure_preserves_previous_folder(tmp_path, monkeypatch):
    destination = tmp_path / "test_images"
    destination.mkdir()
    (destination / "previous.jpg").write_bytes(b"previous session")
    original_rename = type(destination).rename

    def fail_publish(path, target):
        if path.name.startswith(".spacegit-capture-"):
            raise OSError("Destination unavailable")
        return original_rename(path, target)

    monkeypatch.setattr(type(destination), "rename", fail_publish)
    with pytest.raises(OSError, match="Destination unavailable"):
        export_frames(str(destination), {1: (time.time(), {}, b"new session")})
    assert (destination / "previous.jpg").read_bytes() == b"previous session"
    assert list(tmp_path.iterdir()) == [destination]


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


@pytest.mark.parametrize("origin", ["http://127.0.0.1:3000", "http://127.0.0.1:3101"])
@pytest.mark.parametrize("port", [8000, 8002])
def test_capture_can_connect_via_a_loopback_session(tmp_path, monkeypatch, origin, port):
    monkeypatch.setenv("SPACEGIT_LOCAL_SESSION", "1")
    monkeypatch.setenv("SPACEGIT_EDGE_PORT", str(port))
    app = make_app(path=tmp_path / "db.sqlite", mode="demo", token=TOKEN)
    with TestClient(app, base_url=f"http://127.0.0.1:{port}", client=("127.0.0.1", 15000)) as client:
        path = "/api/v1/local-session"
        headers = {"Origin": origin, "X-SpaceGit-Local": "1"}
        assert client.post(path, headers={"Origin": origin}).status_code == 403
        assert client.post(path, headers={**headers, "X-Forwarded-For": "127.0.0.1"}).status_code == 403
        assert client.post(path, headers={**headers, "Origin": "https://example.org"}).status_code == 403
        assert client.post(path, headers={**headers, "Host": "127.0.0.1:9002"}).status_code == 403
        session = client.post(path, headers=headers).json()["token"]
        auth = {"Authorization": f"Bearer {session}"}
        assert client.get("/api/v1/rig", headers={**auth, "Origin": origin}).status_code == 200
        assert client.get("/api/v1/rig", headers={**auth, "Origin": "http://localhost:3000"}).status_code == 401


def test_demo_never_opens_or_claims_live_cameras(tmp_path):
    with TestClient(make_app(path=tmp_path / "db.sqlite", mode="demo", token=TOKEN)) as client:
        assert {item["status"] for item in client.get("/api/v1/rig",headers=AUTH).json()["feeds"]} == {"simulated"}
        assert client.post("/api/v1/rig/start",headers=AUTH).status_code == 409
        assert client.post("/api/v1/rig/captures",headers=AUTH).status_code == 409

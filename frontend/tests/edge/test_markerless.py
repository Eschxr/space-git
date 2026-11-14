import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from spacegit_edge.camera import Camera
from spacegit_edge.camera_diagnostics import CameraDiagnostics
from spacegit_edge import devices
from spacegit_edge.geometry import CHECK, FIT
from spacegit_edge.main import make_app
from test_edge import AUTH, TOKEN


def test_camera_workspace_tracks_unprinted_object_and_preserves_history(tmp_path, monkeypatch):
    app = make_app(tmp_path/"markerless.sqlite3", "live", TOKEN)
    rng = np.random.default_rng(42)
    texture = rng.integers(20, 230, (104, 125), dtype=np.uint8)
    texture = cv2.GaussianBlur(texture, (3, 3), 0)
    signature = {"index": 1, "resolution": [640, 480], "dictionary": "DICT_4X4_250"}
    position = [126, 112]

    def frame(_camera):
        image = np.full((480, 640), 80, np.uint8)
        if position:
            x, y = position
            image[y:y+104, x:x+125] = texture
        return (time.time(), {}, cv2.imencode(".jpg", image)[1].tobytes()), signature

    def until(client, predicate, timeout=4):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            live = client.get("/api/v1/status", headers=AUTH).json()["live"]
            if live and predicate(live):
                return live
            time.sleep(.045)
        raise AssertionError(live)

    monkeypatch.setattr(Camera, "calibration_frame", frame)
    monkeypatch.setattr(devices, "monitor_layout", lambda: [
        {"id": "main", "rect": [0, 0, 1280, 720]}, {"id": "projector", "rect": [1280, 0, 1280, 720]},
    ])
    with TestClient(app) as client:
        app.state.runtime.camera.signature = signature

        def post(path, data):
            response = client.post("/api/v1"+path, headers=AUTH, json=data)
            assert response.is_success, response.text
            return response.json()

        workspace = post("/workspace", {"corners": [[30, 30], [610, 30], [610, 450], [30, 450]],
                                       "size_m": [2.9, 2.1]})
        assert workspace["units"] == "m"
        selected = post("/tracking", {"name": "Textured notebook", "box": [126, 112, 251, 216]})
        marker = selected["marker"]
        live = until(client, lambda value: any(p["marker"] == marker for p in value["poses"]))
        assert not live["projection_ready"]
        history = app.state.runtime.store.list()
        expected = history["branches"]["main"]
        first = post("/tracking/commit", {"branch": "main", "expected": expected, "message": "First observation"})
        position[:] = [285, 193]
        moved = until(client, lambda value: any(p["x"] > 1.4 for p in value["poses"]))
        assert moved["poses"][0]["id"] == selected["id"]
        second = post("/tracking/commit", {"branch": "main", "expected": first["id"], "message": "Moved notebook"})
        assert second["parents"] == [first["id"]]
        assert second["scene"]["objects"][0]["x"] - first["scene"]["objects"][0]["x"] > .7

        projector = {"id": "projector", "width": 1280, "height": 720, "screen": [1280, 0],
                     "fullscreen": True, "automatic_calibration": True}
        post("/projector", projector)
        for i in range(12):
            displayed = post(f"/calibration/point/{i}?projection_only=true", {})["wizard"]
            post("/projector", dict(projector, wizard_key=displayed["key"]))
        points = [(12+615*x, 10+460*y) for x, y in FIT+CHECK]
        post("/calibration/projection", {"fit": points[:6], "check": points[6:]})
        until(client, lambda value: value["projection_ready"])
        post("/deployments", {"commit": first["id"], "tolerance_mm": 30, "dwell_s": .35})
        guiding = until(client, lambda value: value["state"] == "MOVING")
        assert guiding["overlay"]["arrow"]

        position.clear()
        lost = until(client, lambda value: any(p["status"] == "LOST" for p in value["tracked"]))
        assert lost["poses"] == []
        assert lost["state"] == "TRACKING_LOST" and lost["overlay"] is None
        refused = client.post("/api/v1/tracking/commit", headers=AUTH,
                              json={"branch": "main", "expected": second["id"], "message": "Occluded"})
        assert refused.status_code == 409
        position[:] = [126, 112]
        recovered = until(client, lambda value: bool(value["poses"]))
        assert recovered["poses"][0]["id"] == selected["id"]
        assert abs(recovered["poses"][0]["x"] - first["scene"]["objects"][0]["x"]) < .04
        until(client, lambda value: value["plan"]["done"] and value["state"] == "VERIFIED")
        confirmed = post("/deployments/active/confirm", {})
        assert confirmed["revision"] not in (first["id"], second["id"])
        assert app.state.runtime.store.list()["branches"]["main"] == second["id"]


def test_camera_diagnostics_report_observed_delivery():
    diagnostics = CameraDiagnostics()
    frame = np.full((180, 320, 3), 10, np.uint8)
    start = time.time()-1
    for index in range(21):
        result = diagnostics.observe(frame, start+index/20, 30)
    assert result["grade"] == "Unsuitable"
    assert result["underexposed"] == 1
    assert abs(result["fps"]-20) < .01
    assert abs(result["delivery_shortfall"]-1/3) < .01

import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from spacegit_edge import auto_calibration, devices
from spacegit_edge.camera import Camera
from spacegit_edge.main import make_app
from test_edge import AUTH, TOKEN


@pytest.mark.parametrize("visible", [True, False])
@pytest.mark.parametrize("projection_only", [True, False])
def test_automatic_calibration_uses_acknowledged_camera_frames(tmp_path, monkeypatch, visible, projection_only):
    app = make_app(tmp_path/"live.sqlite3", "live", TOKEN)
    signature = {"index": 2, "resolution": [640, 400], "dictionary": "DICT_4X4_250"}
    centers = [(80, 340), (560, 340), (560, 60), (80, 60)]
    anchors = {i: [[x-6, y-6], [x+6, y-6], [x+6, y+6], [x-6, y+6]]
               for i, (x, y) in enumerate(centers)}
    dark = np.full((400, 640), 50, dtype=np.uint8)
    for x, y in centers:
        cv2.circle(dark, (x, y), 6, 170, -1)
    frames = {}

    def simulated_frame(_camera):
        wizard = app.state.runtime.wizard
        point = tuple(wizard["point"]) if visible and wizard and wizard["kind"]=="auto_spot" else None
        if point not in frames:
            image = dark.copy()
            if point:
                image += 5  # Simulate a small global exposure shift.
                x, y = point
                cv2.circle(image, (round(115+400*x), round(82+240*y)), 5, 230, -1)
            frames[point] = cv2.imencode(".jpg", image)[1].tobytes()
        return (time.time(), {} if projection_only else anchors, frames[point]), signature

    monkeypatch.setattr(Camera, "calibration_frame", simulated_frame)
    monkeypatch.setattr(devices, "monitor_layout", lambda: [
        {"id": "main", "rect": [0, 0, 1920, 1080]}, {"id": "projector", "rect": [1920, 0, 1600, 900]},
    ])
    monkeypatch.setattr(auto_calibration, "DISPLAY_SETTLE_SECONDS", 0)

    with TestClient(app) as client:
        app.state.runtime.camera.signature = signature
        def post(path, data):
            return client.post("/api/v1"+path, headers=AUTH, json=data)

        def status():
            return client.get("/api/v1/status", headers=AUTH).json()

        deadline = time.monotonic()+1
        while status()["display_count"] != 2 and time.monotonic() < deadline:
            time.sleep(.01)
        settings = {"limit_px": 8} if projection_only else {"wall": [2.4, 1.4], "marker_m": .06, "limit_px": 8}
        assert post("/calibration/automatic", settings).status_code == 409
        projector = {"id": "test-projector", "width": 1600, "height": 900, "screen": [1920, 0],
                     "fullscreen": True, "automatic_calibration": True}
        post("/projector", projector).raise_for_status()
        assert post("/calibration/automatic", settings).status_code == 202
        assert post("/calibration/point/0", {}).status_code == 409
        deadline = time.monotonic()+9
        while time.monotonic() < deadline:
            snapshot = status()
            if snapshot["automatic_calibration"]["state"] != "running":
                break
            wizard = snapshot["wizard"]
            if wizard:
                post("/projector", {**projector, "wizard_key": wizard["key"]}).raise_for_status()
            time.sleep(.025)
        result = snapshot["automatic_calibration"]
        assert snapshot["wizard"] is None
        if visible:
            assert result["state"] == "complete", result
            assert result["completed"] == 12
            assert result["max_px"] < 6
            profile = snapshot["projection_preview" if projection_only else "calibration"]
            assert profile["display_fingerprint"]["output"] == [1600, 900]
            if projection_only:
                assert snapshot["calibration"] is None
                rectified = client.get("/api/v1/preview?projection=true", headers=AUTH)
                image = cv2.imdecode(np.frombuffer(rectified.content, np.uint8), cv2.IMREAD_GRAYSCALE)
                assert image.shape == (540, 960)
                post("/projector", {**projector, "width": 1280}).raise_for_status()
                assert status()["projection_preview"] is None
        else:
            assert result["state"] == "failed", result
            assert "could not see" in result["error"]
            assert snapshot["calibration"] is None
            assert snapshot["projection_preview"] is None

"""Acquire camera correspondences from alternating blank and illuminated projection frames."""
import asyncio
import logging
import time
from uuid import uuid4

import cv2
import numpy as np

from .geometry import CHECK, FIT
from .models import CalibrationInput, CalibrationSettings


log = logging.getLogger(__name__)
DISPLAY_SETTLE_SECONDS = .24


def detect_spot(dark, lit, anchors):
    """Locate the newly illuminated spot, optionally inside the wall anchors."""
    if dark.shape != lit.shape or dark.ndim != 2:
        raise ValueError("Camera image size changed during calibration.")
    wall_pixels = np.ones(dark.shape, dtype=bool)
    if anchors:
        wall = np.rint([np.mean(anchors[i], axis=0) for i in range(4)]).astype(np.int32)
        mask = np.zeros(dark.shape, dtype=np.uint8)
        cv2.fillConvexPoly(mask, cv2.convexHull(wall), 1)
        wall_pixels = mask.astype(bool)
    wall_area = np.count_nonzero(wall_pixels)
    if wall_area < 1000:
        raise ValueError("The calibration region must cover more of the webcam image.")
    delta = lit.astype(np.int16) - dark.astype(np.int16)
    # Compensate for mild global exposure shifts without amplifying local noise.
    delta -= int(np.median(delta[wall_pixels]))
    noise = np.percentile(np.abs(delta[wall_pixels]), 90)
    signal = cv2.GaussianBlur(delta.astype(np.float32), (3, 3), 0)
    threshold = max(16, 4 * noise)
    visible = (wall_pixels & (signal >= threshold)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(visible, connectivity=8)
    candidates = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if not 8 <= area <= 0.012 * wall_area:
            continue
        if min(w, h) < 3 or max(w, h) > 4 * min(w, h) or area < 0.35 * w * h:
            continue
        component = labels[y:y+h, x:x+w] == i
        ys, xs = np.nonzero(component)
        weights = signal[y:y+h, x:x+w][component]
        candidates.append((float(weights.sum()), (float(x+np.average(xs, weights=weights)),
                                                  float(y+np.average(ys, weights=weights)))))
    candidates.sort(reverse=True)
    if not candidates:
        raise ValueError("Webcam could not see the projected dot. Aim it at the entire projection and reduce glare.")
    if len(candidates) > 1 and candidates[1][0] >= 0.55 * candidates[0][0]:
        raise ValueError("More than one bright spot appeared. Reduce reflections and keep the wall still.")
    return candidates[0][1]


def read_pair(blank_frames, lit_frames, anchors):
    def decode(data):
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Could not decode a webcam frame.")
        return image

    baseline = np.median([decode(frame) for frame in blank_frames], axis=0).astype(np.uint8)
    observations = [detect_spot(baseline, decode(frame), anchors) for frame in lit_frames]
    center = np.median(observations, axis=0)
    if np.max(np.linalg.norm(np.asarray(observations)-center, axis=1)) > 2.5:
        raise ValueError("The projected dot moved between webcam frames. Keep the camera and wall still.")
    return tuple(center.tolist())


async def collect_frames(runtime, index, point, kind, projector_id):
    wizard = {"index": index, "point": point, "kind": kind, "key": uuid4().hex, "shown": False}
    runtime.wizard = wizard
    deadline = time.monotonic() + 4
    last_stamp = 0
    frames = []
    while time.monotonic() < deadline:
        frame, _ = runtime.calibrating()
        display = runtime.display()
        if runtime.wizard is not wizard or not display or display["id"] != projector_id:
            raise ValueError("The projector changed during automatic calibration.")
        shown_at = wizard.get("shown_at")
        if shown_at is not None and frame[0] > max(last_stamp, shown_at + DISPLAY_SETTLE_SECONDS) and frame[2]:
            frames.append(frame[2])
            last_stamp = frame[0]
            if len(frames) == 3:
                return frames
        await asyncio.sleep(.035)
    raise ValueError("Timed out waiting for the fullscreen projector and fresh webcam frames.")


async def run_automatic(runtime, settings, display):
    coordinates = []
    anchors = runtime.fit_lock["anchors"]
    status = runtime.automatic
    try:
        for index, point in enumerate(FIT + CHECK):
            blank = await collect_frames(runtime, index, point, "auto_blank", display["id"])
            lit = await collect_frames(runtime, index, point, "auto_spot", display["id"])
            try:
                coordinates.append(await asyncio.to_thread(read_pair, blank, lit, anchors))
            except ValueError as exc:
                raise ValueError(f"Point {index+1}/12: {exc}") from exc
            status["completed"] = len(coordinates)
        fit, check = coordinates[:len(FIT)], coordinates[len(FIT):]
        if isinstance(settings, CalibrationSettings):
            request = CalibrationInput(**settings.model_dump(), output=(display["width"], display["height"]),
                                       fit=fit, check=check)
            result = runtime.save_calibration(request)
        else:
            result = runtime.save_projection(fit, check, settings.limit_px)
        status.update(state="complete", max_px=result["max_px"])
    except asyncio.CancelledError:
        status["state"] = "cancelled"
        raise
    except ValueError as exc:
        status.update(state="failed", error=str(exc))
    except Exception:
        log.exception("Automatic projector calibration failed")
        status.update(state="failed", error="Automatic calibration could not finish. Check the edge log and retry.")
    finally:
        runtime.clear_wizard()

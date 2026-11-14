import math
import os
from threading import Lock, Thread
import time

import cv2
import numpy as np

from .geometry import mapped
from .quality import correct_pixels
from .camera_diagnostics import CameraDiagnostics


def detect(frame, dictionary):
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,dictionary)),params)
    points, ids, _ = detector.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    if ids is None:
        return {}
    keys = ids.flatten().tolist()
    return {i:p[0].astype(float).tolist() for i,p in zip(keys,points) if keys.count(i)==1}


def wall_preview(jpeg, markers, aspect):
    """Show the rectangle between anchor centers with anchor 3 at the top left."""
    order = (3, 2, 1, 0)
    if not all(anchor in markers for anchor in order):
        return jpeg
    source = np.asarray([np.mean(markers[anchor], axis=0) for anchor in order], dtype=np.float32)
    if not cv2.isContourConvex(source) or cv2.contourArea(source) < 400:
        return jpeg
    return rectified_preview(jpeg, source, aspect)


def rectified_preview(jpeg, corners, aspect):
    width = max(2, round(960 * min(1, aspect)))
    height = max(2, round(960 * min(1, 1 / aspect)))
    target = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return jpeg
    transform = cv2.getPerspectiveTransform(np.asarray(corners, np.float32), target)
    result = cv2.warpPerspective(image, transform, (width, height))
    ok, cropped = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return cropped.tobytes() if ok else jpeg


class Camera:
    def __init__(self):
        self.lock = Lock()
        self.thread = None
        self.device_index = None
        self.generation = 0
        self.latest = None
        self.error = "Camera is stopped"
        self.signature = None
        self.metrics = None

    def start(self, settings):
        self.stop()
        with self.lock:
            generation = self.generation
            self.device_index = settings.index
            self.error = "Opening camera"
        self.thread = Thread(target=self._run, args=(settings,generation), daemon=True)
        self.thread.start()

    def stop(self):
        with self.lock:
            self.generation += 1
            self.device_index = None
            self.latest = None
            self.signature = None
            self.metrics = None
            self.error = "Camera is stopped"
        if self.thread and self.thread.is_alive():
            self.thread.join(2)

    def _run(self, settings, generation):
        cap = cv2.VideoCapture(settings.index, cv2.CAP_DSHOW if os.name=="nt" else cv2.CAP_ANY)
        try:
            if not cap.isOpened():
                raise RuntimeError(f"Camera {settings.index} could not be opened")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.height)
            diagnostics = CameraDiagnostics()
            nominal_fps = cap.get(cv2.CAP_PROP_FPS)
            if not np.isfinite(nominal_fps) or not 1 <= nominal_fps <= 240:
                nominal_fps = 0
            while generation == self.generation:
                ok, frame = cap.read()
                now = time.time()
                if not ok:
                    raise RuntimeError("Camera frames stopped. Check USB and reconnect in Setup.")
                markers = detect(frame,settings.dictionary)
                signature = dict(index=settings.index, resolution=list(frame.shape[1::-1]), dictionary=settings.dictionary)
                view = frame.copy()
                if markers:
                    cv2.aruco.drawDetectedMarkers(view,[np.array([p],np.float32) for p in markers.values()],
                                                  np.array(list(markers),np.int32).reshape(-1,1))
                encoded, jpg = cv2.imencode(".jpg",view,[cv2.IMWRITE_JPEG_QUALITY,72])
                metrics = diagnostics.observe(frame, now, nominal_fps)
                with self.lock:
                    if generation == self.generation:
                        self.signature = signature
                        self.metrics = metrics
                        self.latest = (now, markers, jpg.tobytes() if encoded else None)
                        self.error = None
        except (cv2.error, RuntimeError) as exc:
            with self.lock:
                if generation == self.generation:
                    self.latest = None
                    self.device_index = None
                    self.signature = None
                    self.metrics = None
                    self.error = str(exc)
        finally:
            cap.release()

    def frame(self):
        with self.lock:
            if not self.latest or time.time()-self.latest[0]>.65:
                return None
            return self.latest

    def calibration_frame(self):
        with self.lock:
            if not self.latest or time.time()-self.latest[0]>.65:
                return None, None
            return self.latest, self.signature


class Tracker:
    def __init__(self):
        self.time = 0
        self.last = {}
        self.poses = []
        self.anchor_time = {}
        self.drift = False

    def ingest(self, timestamp, markers, calibration):
        if timestamp <= self.time:
            return
        self.time = timestamp
        for key, reference in calibration["anchors"].items():
            i = int(key)
            if i in markers:
                self.anchor_time[i] = timestamp
                delta = np.linalg.norm(np.array(reference)-markers[i],axis=1)
                if float(np.max(delta))>9:
                    self.drift = True
        poses = []
        for i, p in markers.items():
            if i < 4:
                continue
            polygon=np.asarray(p,np.float32)
            if cv2.contourArea(polygon)<100:
                continue
            pts = mapped(calibration["camera_to_wall"], correct_pixels(p,calibration.get("intrinsics")))
            x,y = np.mean(pts,axis=0)
            dx,dy = pts[1]-pts[0]
            angle = math.atan2(dy,dx)
            prior = self.last.get(i)
            if prior and timestamp-prior[0]<.22:
                _,px,py,pa = prior[:4]
                if math.hypot(x-px,y-py)>.18:
                    # Require a second nearby reading before accepting a large jump.
                    if len(prior)==4:
                        self.last[i]=(prior[0],px,py,pa,float(x),float(y))
                        continue
                    if math.hypot(x-prior[4],y-prior[5])>.04:
                        self.last[i]=(prior[0],px,py,pa,float(x),float(y))
                        continue
                else:
                    x,y=px+.55*(x-px),py+.55*(y-py)
                    angle=math.remainder(pa+.55*math.remainder(angle-pa,2*math.pi),2*math.pi)
            self.last[i]=(timestamp,float(x),float(y),angle)
            poses.append(dict(marker=i,x=float(x),y=float(y),angle=angle,confidence=min(1.,cv2.contourArea(polygon)/350)))
        self.poses=poses

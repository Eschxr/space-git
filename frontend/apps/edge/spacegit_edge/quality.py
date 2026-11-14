"""Calibration checks and latency measurements. Never substitute fixture data for hardware."""
from collections import OrderedDict, deque
import hashlib
import json
import math

import cv2
import numpy as np

from .geometry import mapped

PATTERN = (9, 6)  # inner corners on a 10 x 7 square board
MIN_VIEWS = 10


def correct_pixels(points, intrinsics=None):
    points = np.asarray(points, np.float64).reshape(-1, 2)
    if not intrinsics:
        return points
    k=np.asarray(intrinsics["matrix"], np.float64)
    return cv2.undistortPoints(points.reshape(-1,1,2), k, np.asarray(intrinsics["distortion"]), P=k).reshape(-1,2)


def board_view(jpg):
    frame=cv2.imdecode(np.frombuffer(jpg,np.uint8),cv2.IMREAD_GRAYSCALE)
    if frame is None:
        raise ValueError("Camera preview unavailable")
    found,p=cv2.findChessboardCornersSB(frame,PATTERN)
    if not found:
        raise ValueError("Show the complete 10 × 7 checkerboard without glare, cropping or blur")
    return p.reshape(-1,2)


def view_signature(corners, resolution):
    normal=np.asarray(corners,np.float64)/resolution
    center=normal.mean(axis=0)
    area=cv2.contourArea(cv2.convexHull(normal.astype(np.float32)))
    tilt=np.linalg.norm(normal[0]-normal[8])/max(.001,np.linalg.norm(normal[45]-normal[53]))
    return np.array([*center, math.sqrt(area), .25*math.log(max(.01,tilt))])


def estimate_intrinsics(views, resolution):
    if len(views)<MIN_VIEWS:
        raise ValueError("Collect at least ten distinct checkerboard views")
    signs=np.asarray([view_signature(v,resolution) for v in views])
    if max(np.ptp(signs[:,:2],axis=0))<.26 or min(np.ptp(signs[:,:2],axis=0))<.16 or np.ptp(signs[:,2])<.09:
        raise ValueError("Move the board across all parts of the frame and vary its distance and angle")
    obj=np.zeros((PATTERN[0]*PATTERN[1],3),np.float32)
    obj[:,:2]=np.mgrid[0:PATTERN[0],0:PATTERN[1]].T.reshape(-1,2)
    rms,k,d,rot,trans=cv2.calibrateCamera([obj]*len(views),
                 [np.asarray(v,np.float32).reshape(-1,1,2) for v in views],tuple(resolution),None,None)
    if not np.isfinite(k).all() or not np.isfinite(d).all() or not math.isfinite(rms) or rms>1.5 or min(k[0,0],k[1,1])<min(resolution)*.18:
        raise ValueError("Lens fit did not meet the 1.5 px RMS limit; repeat with sharper, more varied views")
    errors=[float(np.sqrt(np.mean(np.sum((cv2.projectPoints(obj,r,t,k,d)[0].reshape(-1,2)-p)**2,axis=1))))
            for p,r,t in zip(views,rot,trans)]
    if max(errors)>2.5:
        raise ValueError("A checkerboard view exceeded 2.5 px reprojection error")
    return {"matrix":k.tolist(),"distortion":d.ravel().tolist(),"rms_px":rms,"views":len(views),"errors_px":errors}


def fingerprint(display, topology):
    if not display or not display["fullscreen"]:
        return None
    return dict(output=[display["width"],display["height"]],screen=list(display["screen"]),
                display_key=display.get("display_key"),topology=topology)


def geometry_reason(calibration, signature, display, topology):
    if not calibration:
        return "No wall calibration"
    if signature!=calibration["signature"]:
        return "Camera or capture resolution changed"
    active=fingerprint(display,topology)
    if not active:
        return "Projector is not registered fullscreen"
    saved=calibration.get("display_fingerprint")
    if not saved:
        return "Recalibrate once to bind this calibration to the active display"
    if saved!=active:
        return "Projector display, resolution or topology changed; recalibrate"
    return None


def topology_id(monitors):
    if not monitors:
        return None
    packed=json.dumps(sorted(monitors,key=lambda d:d["id"]),sort_keys=True)
    return hashlib.sha256(packed.encode()).hexdigest()[:16]


def physical_point(cal,xy):
    if any(v<0 or v>limit for v,limit in zip(xy,cal["wall"])):
        raise ValueError("Reference point is outside the measured wall")
    p=mapped(cal["wall_to_projector"],[xy])[0]/np.array(cal["output"])
    if not np.isfinite(p).all() or any(v<.04 or v>.96 for v in p):
        raise ValueError("Choose a reference point inside the projector image, away from its edge")
    return p.tolist()


def residuals(expected, measured):
    offset=[(b-a)*1000 for a,b in zip(expected,measured)]
    return {"dx_mm":offset[0],"dy_mm":offset[1],"error_mm":math.hypot(*offset)}


def percentiles(values):
    if not len(values):
        return {"count":0,"p50_ms":None,"p95_ms":None}
    return {"count":len(values),"p50_ms":float(np.percentile(values,50)),
            "p95_ms":float(np.percentile(values,95))}


class Timing:
    def __init__(self):
        self.pending=OrderedDict()
        self.values=deque(maxlen=600)
        self.last_frame=None

    def observe(self, seq, capture_s, display_id):
        if capture_s==self.last_frame:
            return
        self.last_frame=capture_s
        self.pending[seq]=(capture_s*1000,display_id)
        while len(self.pending)>160:
            self.pending.popitem(last=False)

    def collect(self, samples, display_id, wall_ms):
        for s in samples:
            frame=self.pending.get(s.seq)
            if not frame or frame[1]!=display_id:
                continue
            dt=s.paint_ms-frame[0]
            if 0<=dt<=1000 and wall_ms-2500<=s.paint_ms<=wall_ms+25:
                del self.pending[s.seq]
                self.values.append(dt)

    def summary(self):
        return {"provenance":"local_capture_read_to_browser_render_callback",**percentiles(self.values)}

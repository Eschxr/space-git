from contextlib import asynccontextmanager, suppress
from collections import deque
from copy import deepcopy
import asyncio
import hashlib
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import time
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, UnidentifiedImageError
from pydantic import Field, FiniteFloat
import numpy as np
import cv2
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.datastructures import UploadFile

from . import devices
from .auto_calibration import run_automatic
from .camera import Camera, Tracker, rectified_preview, wall_preview
from .geometry import CHECK, FIT, corners, mapped, solve, solve_projector, solve_workspace
from .markerless import ObjectTracker
from .models import Branch, CalibrationInput, CalibrationSettings, CameraInput, Deploy, Diff, Id, JobInput, Merge, ObservationCommit, Pair, ProjectionInput, ProjectionSettings, Save, Scene, Strict, TrackInput, VisualTransform, WorkspaceInput
from .navigation import Plan
from .rig import PoleRig, routes as rig_routes
from .quality import Timing, board_view, estimate_intrinsics, fingerprint, geometry_reason, physical_point, residuals, topology_id, view_signature
from .store import ROOT, Store, compact, issues, new_id


class Paint(Strict):
    seq: int = Field(ge=0)
    paint_ms: FiniteFloat


class Display(Strict):
    width: int = Field(ge=320, le=8192)
    height: int = Field(ge=240, le=8192)
    fullscreen: bool
    id: Id
    screen: tuple[int, int]
    display_key: str | None = Field(default=None,max_length=160)
    screen_label: str | None = Field(default=None,max_length=160)
    wizard_key: Id | None = None
    automatic_calibration: bool = False
    paint: list[Paint] = Field(default_factory=list,max_length=20)


class Reference(Strict):
    xy: Pair


class ReferenceReport(Reference):
    key: Id


class CaptureRequest(Strict):
    quality: Literal["sparse","mesh","mesh_textured","dense","textured"] = "sparse"


ARTIFACTS={
    "sparse.ply":"application/octet-stream", "dense.ply":"application/octet-stream",
    "mesh.ply":"application/octet-stream","model.obj":"text/plain",
    "model.glb":"model/gltf-binary","textured-obj.zip":"application/zip",
}


def registered_job(db,asset):
    row=db.execute("SELECT body FROM jobs WHERE id=? AND stage IN ('complete','partial','cancelled')",(asset,)).fetchone()
    if not row:
        raise HTTPException(404,"Registered asset is unavailable")
    body=json.loads(row[0])
    if body.get("asset")!=asset:
        raise HTTPException(404,"Registered asset is unavailable")
    return body


def photo_device(user_agent):
    return next((label for fragment,label in (("iPhone","iPhone"),("iPad","iPad"),("Android","Android"),
                ("Windows","Windows"),("Macintosh","macOS"),("Linux","Linux")) if fragment in user_agent),"Browser")


class Runtime:
    def __init__(self, path, mode):
        self.mode=mode
        self.store=Store(path)
        self.store.seed(mode=="demo")
        self.camera=Camera()
        self.pole=PoleRig(self.camera,self.store,mode)
        self.tracker=Tracker()
        self.cal=self.store.setting("calibration")
        self.projection_preview=self.store.setting("projection_preview")
        self.workspace = self.store.setting("camera_workspace")
        self.calibration_mode = self.store.setting("calibration_mode") or ("anchors" if self.cal else "markerless")
        self.objects = ObjectTracker()
        self.seq=0
        self.device=new_id()
        self.projector=None
        self.display_count=None
        self.topology=None
        self.monitor_inventory=[]
        self.wizard=None
        self.plan=None
        self.replay=json.loads((ROOT/"fixtures/replay.json").read_text())
        self.replay_start=None
        self.replay_base=None
        self.poses=[]
        self.last=None
        self.pairings={}
        self.timing=Timing()
        self.intrinsics=self.store.setting("intrinsics")
        self.lens_views=[]
        self.lens_signature=None
        self.lens_stamp=None
        self.fit_lock=None
        self.automatic=None
        self.automatic_task=None
        self.stability={}
        if self.mode=="demo":
            scene=self.store.list()["commits"][-1]["scene"]
            w,h=scene["wall"]
            self.cal=dict(id="simulated",wall=[w,h],output=[1600,900],mean_px=0,max_px=0,
                          wall_to_projector=[[1600*.84/w,0,128],[0,-900*.82/h,819],[0,0,1]])
            self.replay_base=[dict(marker=o["marker"],x=o["x"],y=o["y"],angle=o["angle"],confidence=1)
                              for o in scene["objects"]]

    def display(self):
        return self.projector if self.projector and time.monotonic()-self.projector["seen"]<2.6 and self.display_count!=1 else None

    def calibrating(self):
        frame,signature=self.camera.calibration_frame()
        active=fingerprint(self.display(),self.topology)
        if not frame or not active or not self.fit_lock or active!=self.fit_lock["display"] or signature!=self.fit_lock["camera"]:
            raise ValueError("Camera or projector changed during calibration. Restart the crosses.")
        if any(i not in frame[1] or np.max(np.linalg.norm(np.asarray(points)-frame[1][i],axis=1))>9
               for i,points in self.fit_lock["anchors"].items()):
            raise ValueError("Wall anchors moved or were covered during calibration. Restart the crosses.")
        return frame,signature

    def clear_wizard(self):
        self.fit_lock=self.wizard=None

    def require_idle_calibration(self):
        if self.automatic_task and not self.automatic_task.done():
            raise ValueError("Cancel or finish automatic calibration first.")

    def lock_calibration(self, display, *, projection_only=False):
        frame,signature=self.camera.calibration_frame()
        if not frame or not signature:
            raise ValueError("Open the webcam and wait for a live image")
        if not projection_only and any(k not in frame[1] for k in range(4)):
            raise ValueError("All four wall anchors must be visible")
        self.fit_lock={"display":fingerprint(display,self.topology),"camera":signature,
                       "anchors":{} if projection_only else {k:frame[1][k] for k in range(4)}}

    def active_projection(self, signature):
        profile = self.projection_preview
        if profile and signature == profile["signature"] and fingerprint(self.display(), self.topology) == profile["display_fingerprint"]:
            return profile
        return None

    def workspace_profile(self, signature):
        if self.mode != "live" or self.calibration_mode != "markerless" or not signature:
            return None
        projection = self.active_projection(signature)
        workspace = self.workspace
        if workspace:
            if workspace["signature"] != signature:
                return None
        elif projection:
            workspace = dict(id=projection["id"], signature=signature, wall=[1, 1], units="normalized",
                             camera_to_wall=projection["camera_to_wall"])
        else:
            return None
        # Changing the projector invalidates an in-progress restore while retaining
        # camera-only object coordinates in an explicitly configured workspace.
        profile = dict(workspace, workspace_id=workspace["id"], output=signature["resolution"], mean_px=0., max_px=0.)
        if projection:
            matrix = np.asarray(projection["camera_to_projector"]) @ np.linalg.inv(workspace["camera_to_wall"])
            profile.update(id=workspace["id"] + "_" + projection["id"], output=projection["output"],
                           wall_to_projector=matrix.tolist(), display_fingerprint=projection["display_fingerprint"],
                           mean_px=projection["mean_px"], max_px=projection["max_px"])
        return profile

    def current_calibration(self):
        if self.mode == "demo" or self.calibration_mode == "anchors":
            return self.cal
        return self.workspace_profile(self.camera.signature)

    def save_projection(self, fit, check, limit_px):
        _, signature = self.calibrating()
        display = self.fit_lock["display"]
        width, height = display["output"]
        transform, residuals = solve_projector(fit, check, (width, height), signature["resolution"], limit_px)
        projector_corners = np.asarray([(0, 0), (width-1, 0), (width-1, height-1), (0, height-1)])
        inverse = np.linalg.inv(transform)
        depth = projector_corners @ inverse[2, :2] + inverse[2, 2]
        camera_corners = mapped(inverse, projector_corners)
        if np.any(np.abs(depth) < 1e-8) or np.min(depth) * np.max(depth) <= 0 or not cv2.isContourConvex(camera_corners.astype(np.float32)):
            raise ValueError("The projection boundary is unstable. Aim at a flat surface and retry.")
        if np.any(camera_corners < -2) or np.any(camera_corners > np.asarray(signature["resolution"]) + 1):
            raise ValueError("The webcam must see all four corners of the projected image. Widen its view and retry.")
        normalize = np.array([[1 / (width-1), 0, 0], [0, -1 / (height-1), 1], [0, 0, 1]])
        result = dict(id=new_id(), signature=signature, display_fingerprint=display, camera_to_projector=transform.tolist(),
                      camera_to_wall=(normalize @ transform).tolist(),
                      corners=camera_corners.tolist(), output=[width, height], limit_px=limit_px, **residuals)
        self.store.setting("projection_preview", result)
        self.projection_preview = result
        self.store.setting("calibration_mode", "markerless")
        self.calibration_mode = "markerless"
        self.plan = None
        return result

    def save_calibration(self, request):
        frame,signature=self.calibrating()
        display=self.display()
        if (display["width"],display["height"])!=request.output:
            raise ValueError("Output size does not match the fullscreen projector")
        lens=self.intrinsics if self.intrinsics and self.intrinsics["signature"]==signature else None
        result=solve(request,frame[1],signature,lens)
        result["display_fingerprint"]=fingerprint(display,self.topology)
        self.store.setting("calibration",result)
        self.cal=result
        self.store.setting("calibration_mode", "anchors")
        self.calibration_mode = "anchors"
        self.clear_wizard()
        self.tracker=Tracker()
        self.plan=None
        self.timing=Timing()
        self.stability={}
        return result

    def tick(self):
        now=time.time()
        self.seq+=1
        frame,signature=self.camera.calibration_frame()
        ts=frame[0] if frame else None
        anchors=[i for i in frame[1] if i<4] if frame else []
        markerless = self.mode == "live" and self.calibration_mode == "markerless"
        cal=self.workspace_profile(signature) if markerless else self.cal
        tracked = self.objects.snapshot(cal, now) if markerless else []
        display=self.display()
        state="READY"
        reason=None
        if self.mode=="demo":
            ts=now
            self.poses=deepcopy(self.replay_base)
            anchors=list(range(4))
            if self.replay_start is not None:
                i=min(len(self.replay["offsets_m"])-1,int((now-self.replay_start)*1000/self.replay["period_ms"]))
                offset=self.replay["offsets_m"][i]
                self.poses[0]["x"]+=offset
                self.poses[0]["y"]-=offset*.4
                if offset==0:
                    self.replay_start=None
        else:
            if markerless:
                self.poses = [p for p in tracked if p["confidence"] >= .65]
            elif frame and cal and signature==cal["signature"]:
                self.tracker.ingest(ts, frame[1], cal)
                self.poses=self.tracker.poses
            else:
                self.poses=[]
            reason=(None if cal else "Calibrate a workspace or the projector in Setup") if markerless else geometry_reason(cal,signature,display,self.topology)
            if not frame or now-ts>.33:
                state="DISCONNECTED"
                reason="No fresh camera frame"
            elif not cal:
                state="SETUP_REQUIRED"
            elif markerless and self.objects.drifted_workspace == cal["workspace_id"]:
                state="CALIBRATION_DRIFT"
                reason="Camera or workspace motion detected. Recalibrate the workspace."
            elif not markerless and (signature!=cal["signature"] or self.tracker.drift or any(ts-self.tracker.anchor_time.get(i,0)>.35 for i in range(4))):
                state="CALIBRATION_DRIFT"
                reason="Camera geometry changed or an anchor moved / disappeared"
            elif reason or self.wizard is not None:
                state="SETUP_REQUIRED"
                reason=reason or "Calibration cross is active"
            if self.wizard and self.wizard.get("kind")=="physical" and (state=="CALIBRATION_DRIFT" or not display or not frame or
                    geometry_reason(cal,signature,display,self.topology)):
                self.clear_wizard()
            if ts is not None and state=="READY":
                for p in self.poses:
                    if p["confidence"]>=.65:
                        series=self.stability.setdefault(p["marker"],deque(maxlen=180))
                        if not series or series[-1][0]!=ts:
                            series.append((ts,p["x"],p["y"]))
        self.last=dict(version=1,seq=self.seq,timestamp=ts or now,received_ms=max(0,(now-(ts or now))*1000),
                       scene_version=1,device=self.device,mode=self.mode,state=state,poses=self.poses,anchors=anchors,
                       camera=bool(frame),calibration={k:cal[k] for k in ("id","output","mean_px","max_px")} if cal else None,
                       overlay=None,plan=None,calibration_reason=reason,tracked=tracked,
                       units=cal.get("units", "m") if cal else None,
                       projection_ready=bool(cal and cal.get("wall_to_projector") and cal.get("units", "m") == "m" and not reason))
        if self.plan:
            plan=self.plan
            if state=="READY" and (plan.calibration_id!=cal["id"] or not cal.get("wall_to_projector")):
                state="CALIBRATION_DRIFT"
            try:
                observation_stamp = min((p["timestamp"] for p in self.poses), default=None) if markerless else ts
                state=plan.update(now,observation_stamp,self.seq,self.poses,state,cal,self.store.record)
                if self.mode=="live" and not markerless and plan.completed and state=="VERIFIED" and not plan.saved and not plan.save_error and len(plan.objects)==len(plan.commit["scene"]["objects"]):
                    plan.saved=self.store.save_verified(plan,self.poses,cal["id"],self.seq,ts)
            except (sqlite3.Error,ValueError) as exc:
                plan.save_error=str(exc)
                state="CONFLICT"
            if plan.save_error:
                state="CONFLICT"
            overlay=plan.overlay(state,self.poses,cal)
            if state=="MOVING" and overlay is None:
                state="TRACKING_LOST"
            if self.mode=="live" and display and overlay and ts is not None:
                self.timing.observe(self.seq,ts,display["id"])
            self.last.update(state=state,overlay=overlay,plan=dict(id=plan.id,index=min(plan.index,len(plan.objects)),
                total=len(plan.objects),done=plan.completed,saved=plan.saved,save_error=plan.save_error))
        return self.last


def make_app(path=None, mode=None, token=None):
    root=Path(os.getenv("SPACEGIT_DATA",ROOT/"data")).resolve()
    mode=mode or os.getenv("SPACEGIT_MODE","live")
    if mode not in ("demo","live"):
        raise RuntimeError("SPACEGIT_MODE must be live or demo")
    path=Path(path or root/f"{mode}.sqlite3")
    files=path.parent/f"{path.stem}-files"
    token=token or os.getenv("SPACEGIT_TOKEN")
    origins=["http://localhost:3000","http://127.0.0.1:3000"]
    local_session_secret = secrets.token_bytes(32) if os.getenv("SPACEGIT_LOCAL_SESSION") == "1" else None
    mobile=os.getenv("SPACEGIT_MOBILE_ORIGIN","").rstrip("/")
    if mobile and not mobile.startswith("https://"):
        raise RuntimeError("SPACEGIT_MOBILE_ORIGIN requires HTTPS")
    if mobile:
        origins.append(mobile)

    @asynccontextmanager
    async def lifespan(app):
        if not token or len(token)<24:
            raise RuntimeError("Set SPACEGIT_TOKEN to a random string of at least 24 characters")
        app.state.runtime=Runtime(path,mode)
        async def loop():
            while True:
                app.state.runtime.tick()
                await asyncio.sleep(.04)
        task=asyncio.create_task(loop())
        async def track_objects():
            rt = app.state.runtime
            while True:
                frame, signature = rt.camera.calibration_frame()
                profile = rt.workspace_profile(signature)
                if frame and frame[2] and profile and not rt.wizard:
                    try:
                        await asyncio.to_thread(rt.objects.observe, frame, profile)
                    except (ValueError, cv2.error):
                        pass  # Old observations expire if processing cannot produce a fresh pose.
                await asyncio.sleep(.045)
        tracking_task = asyncio.create_task(track_objects()) if mode == "live" else None
        async def monitors():
            while True:
                layout=await asyncio.to_thread(devices.monitor_layout)
                rt=app.state.runtime
                rt.monitor_inventory=layout
                rt.display_count=len(layout) if layout else await asyncio.to_thread(devices.displays)
                rt.topology=topology_id(layout)
                await asyncio.sleep(.6)
        monitors_task=asyncio.create_task(monitors()) if mode=="live" else None
        try:
            yield
        finally:
            task.cancel()
            if tracking_task:
                tracking_task.cancel()
                with suppress(asyncio.CancelledError):
                    await tracking_task
            automatic_task=app.state.runtime.automatic_task
            if automatic_task:
                automatic_task.cancel()
                with suppress(asyncio.CancelledError):
                    await automatic_task
            if monitors_task:
                monitors_task.cancel()
                with suppress(asyncio.CancelledError):
                    await monitors_task
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.to_thread(app.state.runtime.pole.stop)
            await asyncio.to_thread(app.state.runtime.camera.stop)

    app=FastAPI(title="SpaceGit Edge",version="1.0",lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","[::1]","testserver"])
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=["GET","POST","DELETE"],
                       allow_headers=["Authorization","Content-Type","X-SpaceGit-Local"])

    @app.middleware("http")
    async def private(request,call_next):
        response=await call_next(request)
        response.headers["Cache-Control"]="no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        return response

    @app.exception_handler(ValueError)
    async def invalid(_request,exc):
        return JSONResponse({"detail":str(exc)},status_code=409)

    def runtime():
        return app.state.runtime

    def sign_session(origin, payload):
        return hmac.digest(local_session_secret, f"{origin}:{payload}".encode(), "sha256").hex()

    def session_valid(supplied, origin):
        if local_session_secret is None or origin not in origins[:2] or len(supplied) > 128:
            return False
        match = re.fullmatch(r"(local\.([0-9]{1,12})\.[a-zA-Z0-9_-]{22})\.([0-9a-f]{64})", supplied)
        if not match:
            return False
        payload, expiry, signature = match.groups()
        return int(expiry) > time.time() and secrets.compare_digest(signature, sign_session(origin, payload))

    def operator(supplied, origin):
        return secrets.compare_digest(supplied.encode(), token.encode()) or session_valid(supplied, origin)

    @app.post("/api/v1/local-session")
    def local_session(request: Request, origin: str = Header(default=""), authorization: str = Header(default="")):
        if local_session_secret is None:
            raise HTTPException(404, "Automatic local connection is unavailable")
        if (origin not in origins[:2] or not request.client or request.client.host not in ("127.0.0.1", "::1")
                or request.headers.get("host") not in ("127.0.0.1:8000", "localhost:8000")
                or request.headers.get("x-spacegit-local") != "1"
                or any(name == "forwarded" or name.startswith("x-forwarded-") for name in request.headers)):
            raise HTTPException(403, "Automatic connection requires the local Studio")
        supplied = authorization.removeprefix("Bearer ")
        if session_valid(supplied, origin) and int(supplied.split(".")[1]) > time.time() + 600:
            return {"token": supplied}
        payload = f"local.{int(time.time())+7200}.{secrets.token_urlsafe(16)}"
        return {"token": f"{payload}.{sign_session(origin, payload)}"}

    def authorize(authorization: str=Header(default=""), origin: str=Header(default="")):
        if origin and origin not in origins[:2]:
            raise HTTPException(403,"Hardware control is local only")
        if not authorization.startswith("Bearer ") or not operator(authorization[7:], origin):
            raise HTTPException(401,"Enter the local operator key")
        return runtime()

    def mobile_lease(rt,authorization,origin):
        lease=rt.pairings.get(authorization[7:]) if authorization.startswith("Bearer ") else None
        if not mobile or origin!=mobile or not lease or time.time()>lease[1]:
            raise HTTPException(401,"Capture link expired or unavailable")
        return lease

    def new_capture(rt,commit,source):
        ident=new_id()
        stamp=time.time()
        with rt.store.tx(True) as db:
            rt.store.commit(db,commit)
            db.execute("INSERT INTO capture_sessions VALUES(?,?,?,?,NULL)",(ident,commit,stamp,source))
        return {"id":ident,"commit":commit,"created":stamp,"source":source}

    def capture_summary(db,ident):
        row=db.execute("SELECT revision,created,source,request_quality FROM capture_sessions WHERE id=?",(ident,)).fetchone()
        if not row:
            raise HTTPException(404,"Capture session not found")
        photos=[r[0] for r in db.execute("SELECT photo FROM capture_entries WHERE session=? ORDER BY rowid",(ident,))]
        return {"id":ident,"commit":row[0],"created":row[1],"source":row[2],"request_quality":row[3],"photos":photos,"count":len(photos)}

    @app.get("/health")
    def health():
        return {"status":"ok","version":1,"mode":mode}

    @app.get("/api/v1/status")
    async def status(rt=Depends(authorize)):
        return {"live":rt.last,"camera_error":rt.camera.error,"camera_signature":rt.camera.signature,
                "projector":rt.display(),"wizard":rt.wizard,"calibration":rt.cal,
                "intrinsics":rt.intrinsics,"lens_views":len(rt.lens_views),"automatic_calibration":rt.automatic,
                "display_count":rt.display_count,"monitors":rt.monitor_inventory,
                "projection_preview":rt.active_projection(rt.camera.signature),
                "camera_metrics":rt.camera.metrics,"workspace":rt.workspace_profile(rt.camera.signature)}

    @app.get("/api/v1/devices")
    def get_devices(rt=Depends(authorize)):
        return {"cameras":devices.cameras(),"displays":devices.displays(),"monitors":rt.monitor_inventory}

    @app.get("/api/v1/workspace")
    def workspace(rt=Depends(authorize)):
        return rt.workspace_profile(rt.camera.signature)

    @app.post("/api/v1/workspace")
    async def set_workspace(req:WorkspaceInput,rt=Depends(authorize)):
        rt.require_idle_calibration()
        frame, signature = rt.camera.calibration_frame()
        if mode != "live" or not frame or not signature:
            raise ValueError("Open the webcam before calibrating a workspace")
        size = req.size_m or (1, 1)
        transform = solve_workspace(req.corners, size, signature["resolution"])
        profile = dict(id=new_id(), signature=signature, corners=req.corners, wall=size,
                       units="m" if req.size_m else "normalized", camera_to_wall=transform.tolist())
        rt.store.setting("camera_workspace", profile)
        rt.store.setting("calibration_mode", "markerless")
        rt.workspace, rt.calibration_mode = profile, "markerless"
        rt.plan = None
        rt.clear_wizard()
        return rt.workspace_profile(signature)

    @app.post("/api/v1/tracking")
    async def start_tracking(req:TrackInput,rt=Depends(authorize)):
        rt.require_idle_calibration()
        frame, signature = rt.camera.calibration_frame()
        profile = rt.workspace_profile(signature)
        if not profile or not frame or not frame[2] or rt.objects.drifted_workspace == profile["workspace_id"]:
            raise ValueError("Open a webcam and calibrate the workspace first")
        revisions = rt.store.list()["commits"]
        registered = {obj["id"]: obj["marker"] for rev in revisions for obj in rev["scene"]["objects"]}
        registered.update({obj["id"]: key for key, obj in rt.objects.targets.items()})
        if req.object_id:
            if req.object_id not in registered:
                raise ValueError("Choose an object from a saved revision to reselect it")
            key, object_id = registered[req.object_id], req.object_id
        else:
            used = set(registered.values()) | set(rt.objects.targets)
            key = next((i for i in range(249, 3, -1) if i not in used), None)
            if key is None:
                raise ValueError("No tracking IDs are available")
            object_id = new_id()
        return rt.objects.add(req.name, req.box, frame, profile, key, object_id)

    @app.delete("/api/v1/tracking/{key}")
    async def stop_tracking(key:int,rt=Depends(authorize)):
        rt.objects.remove(key)
        return {"status":"stopped"}

    @app.post("/api/v1/tracking/commit")
    async def commit_tracking(req:ObservationCommit,rt=Depends(authorize)):
        frame, signature = rt.camera.calibration_frame()
        profile = rt.workspace_profile(signature)
        if (not profile or profile["units"] != "m" or not frame or rt.wizard
                or rt.objects.drifted_workspace == profile["workspace_id"]):
            raise ValueError("Calibrate a workspace with measured dimensions before saving a metric revision")
        observed = rt.objects.snapshot(profile, time.time())
        if not observed or any(p["confidence"] < .65 for p in observed):
            raise ValueError("All tracked objects must be visible and confidently matched")
        with rt.store.tx() as db:
            previous = rt.store.commit(db, req.expected)["scene"]
        prior = {p["id"]: p for p in previous["objects"]}
        objects = [dict(id=p["id"], marker=p["marker"], name=p["name"], x=p["x"], y=p["y"], angle=p["angle"],
                        w=prior.get(p["id"], p)["w"], h=prior.get(p["id"], p)["h"],
                        d=prior.get(p["id"], {}).get("d", .02)) for p in observed]
        unseen = [p for p in previous["objects"] if p["id"] not in {o["id"] for o in objects}]
        if unseen and not np.allclose(previous["wall"], profile["wall"], atol=.002, rtol=0):
            raise ValueError("The previous layout has a different workspace size. Update its geometry in the 3D workspace first.")
        objects.extend(unseen)
        scene = Scene.model_validate(dict(previous, wall=profile["wall"], objects=objects))
        return rt.store.save(req.branch, req.expected, scene, req.message, dict(mode="live", calibration=profile["id"],
                             timestamp=max(p["timestamp"] for p in observed), observations=[
                                 dict(id=p["id"], confidence=p["confidence"], timestamp=p["timestamp"]) for p in observed],
                             unobserved=[p["id"] for p in unseen]))

    @app.post("/api/v1/devices/camera")
    async def camera(req:CameraInput,rt=Depends(authorize)):
        rt.require_idle_calibration()
        if mode!="live":
            raise HTTPException(409,"Start the edge in live mode to open a camera")
        async with rt.pole.lock:
            if rt.pole.enabled and req.index in rt.pole.cameras:
                raise HTTPException(409, "This device is in use by the rig. Stop the rig or select another device.")
            await asyncio.to_thread(rt.camera.start, req)
        rt.tracker=Tracker()
        rt.plan=None
        rt.clear_wizard()
        rt.stability={}
        return {"status":"opening"}

    @app.delete("/api/v1/devices/camera")
    async def stop_camera(rt=Depends(authorize)):
        rt.require_idle_calibration()
        async with rt.pole.lock:
            await asyncio.to_thread(rt.camera.stop)
        rt.clear_wizard()
        return {"status":"stopped"}

    @app.get("/api/v1/preview")
    def preview(wall_aspect: float | None = Query(default=None, ge=0.025, le=40),
                projection: bool = False, rt=Depends(authorize)):
        frame, signature = rt.camera.calibration_frame()
        if not frame or frame[2] is None:
            raise HTTPException(503,"Camera preview unavailable")
        jpeg = frame[2]
        profile = rt.active_projection(signature) if projection else None
        if profile:
            width, height = profile["output"]
            jpeg = rectified_preview(jpeg, profile["corners"], width / height)
        elif wall_aspect is not None:
            jpeg = wall_preview(jpeg, frame[1], wall_aspect)
        return Response(jpeg, media_type="image/jpeg")

    @app.post("/api/v1/projector")
    async def projector(req:Display,rt=Depends(authorize)):
        if mode=="live" and rt.display_count==1:
            raise HTTPException(409,"Only one active display detected. Connect the projector and choose Extend.")
        data=rt.display()
        if data and data["id"]!=req.id and (data["fullscreen"] or not req.fullscreen):
            raise HTTPException(409,"Another projector tab is active")
        rt.projector={**req.model_dump(exclude={"paint","wizard_key"}),"seen":time.monotonic()}
        if req.fullscreen:
            rt.timing.collect(req.paint,req.id,time.time()*1000)
            if rt.wizard and rt.wizard.get("key")==req.wizard_key and not rt.wizard["shown"]:
                rt.wizard["shown"]=True
                rt.wizard["shown_at"]=time.time()
        if rt.wizard and rt.fit_lock and fingerprint(rt.display(),rt.topology)!=rt.fit_lock["display"]:
            rt.clear_wizard()
        calibration = rt.current_calibration()
        if rt.calibration_mode == "markerless" and mode == "live":
            ready = bool(calibration and calibration.get("wall_to_projector") and
                         rt.objects.drifted_workspace != calibration["workspace_id"])
        else:
            ready = not geometry_reason(calibration,rt.camera.signature,rt.display(),rt.topology)
        return {"wizard":rt.wizard,"allow_guidance":mode=="demo" or (not rt.wizard and ready)}

    @app.post("/api/v1/calibration/automatic",status_code=202)
    async def automatic(req:CalibrationSettings | ProjectionSettings,rt=Depends(authorize)):
        rt.require_idle_calibration()
        display=rt.display()
        if mode!="live" or not display or not display["fullscreen"]:
            raise ValueError("Open the local projector on the extended display and enter fullscreen.")
        if not display["automatic_calibration"]:
            raise ValueError("Refresh the local projector page to enable automatic calibration.")
        if rt.wizard:
            raise ValueError("Finish or cancel the current calibration step first.")
        anchored = isinstance(req, CalibrationSettings)
        if anchored and req.marker_m>=min(req.wall)/4:
            raise ValueError("Wall marker size is too large for the measured wall.")
        rt.lock_calibration(display, projection_only=not anchored)
        rt.automatic={"state":"running","completed":0}
        rt.automatic_task=asyncio.create_task(run_automatic(rt,req,display))
        return rt.automatic

    @app.delete("/api/v1/calibration/automatic")
    async def cancel_automatic(rt=Depends(authorize)):
        task=rt.automatic_task
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            rt.automatic["state"]="cancelled"
            rt.clear_wizard()
        return rt.automatic

    @app.post("/api/v1/calibration/point/{i}")
    async def point(i:int,projection_only:bool=False,rt=Depends(authorize)):
        rt.require_idle_calibration()
        if i==-1:
            rt.clear_wizard()
        elif mode=="live" and rt.display() and rt.display()["fullscreen"] and 0<=i<12:
            if i==0:
                rt.lock_calibration(rt.display(), projection_only=projection_only)
                rt.automatic=None
            else:
                rt.calibrating()
                if not rt.wizard or rt.wizard.get("index")!=i-1 or not rt.wizard.get("shown"):
                    raise ValueError("Wait for the previous cross to appear on the projector")
            rt.wizard={"index":i,"point":(FIT+CHECK)[i],"key":new_id(),"shown":False}
        else:
            raise ValueError("Open the projector in fullscreen and select a valid cross")
        return {"wizard":rt.wizard}

    @app.post("/api/v1/calibration/solve")
    async def calibrate(req:CalibrationInput,rt=Depends(authorize)):
        rt.require_idle_calibration()
        display=rt.display()
        if mode!="live" or not display or not display["fullscreen"]:
            raise ValueError("Live webcam and fullscreen projector are required")
        if not rt.wizard or rt.wizard.get("index")!=11 or not rt.wizard.get("shown"):
            raise ValueError("Complete the twelve displayed correspondences first")
        return rt.save_calibration(req)

    @app.post("/api/v1/calibration/projection")
    async def manual_projection(req:ProjectionInput,rt=Depends(authorize)):
        rt.require_idle_calibration()
        if (not rt.wizard or rt.wizard.get("index") != 11 or not rt.wizard.get("shown")
                or not rt.fit_lock or rt.fit_lock["anchors"]):
            raise ValueError("Complete the twelve projected points first")
        result = rt.save_projection(req.fit, req.check, req.limit_px)
        rt.clear_wizard()
        return result

    @app.post("/api/v1/calibration/lens/sample")
    async def sample_lens(rt=Depends(authorize)):
        frame,signature=rt.camera.calibration_frame()
        if mode!="live" or not frame or not frame[2]:
            raise ValueError("Open the live camera before capturing a checkerboard")
        if rt.lens_signature!=signature:
            rt.lens_views=[]
            rt.lens_signature=signature
            rt.lens_stamp=None
        if frame[0]==rt.lens_stamp or len(rt.lens_views)>=24:
            raise ValueError("Move the board before sampling again, or reset the view set")
        p=await asyncio.to_thread(board_view,frame[2])
        if rt.camera.signature!=signature:
            raise ValueError("The camera changed during capture")
        s=view_signature(p,signature["resolution"])
        if any(np.linalg.norm(s-view_signature(v,signature["resolution"]))<.034 for v in rt.lens_views):
            raise ValueError("This view is too similar. Move or tilt the checkerboard")
        rt.lens_views.append(p)
        rt.lens_stamp=frame[0]
        return {"views":len(rt.lens_views)}

    @app.delete("/api/v1/calibration/lens/samples")
    async def reset_lens(rt=Depends(authorize)):
        rt.lens_views=[]
        rt.lens_stamp=None
        return {"views":0}

    @app.post("/api/v1/calibration/lens/solve")
    async def solve_lens(rt=Depends(authorize)):
        rt.require_idle_calibration()
        signature=rt.lens_signature
        if mode!="live" or not signature or signature!=rt.camera.signature:
            raise ValueError("Checkerboard samples must match the current camera")
        result=await asyncio.to_thread(estimate_intrinsics,list(rt.lens_views),signature["resolution"])
        rt.require_idle_calibration()
        if rt.camera.signature!=signature:
            raise ValueError("The camera changed during lens calibration")
        rt.intrinsics={"id":new_id(),"signature":signature,**result}
        rt.store.setting("intrinsics",rt.intrinsics)
        rt.store.clear_setting("calibration")
        rt.cal=rt.plan=None
        rt.clear_wizard()
        return rt.intrinsics

    @app.post("/api/v1/calibration/physical-target")
    async def physical_target(req:Reference,rt=Depends(authorize)):
        rt.require_idle_calibration()
        cal = rt.current_calibration()
        if mode!="live" or not cal or not rt.last or not rt.last["projection_ready"] or rt.last["state"] in ("DISCONNECTED","CALIBRATION_DRIFT","SETUP_REQUIRED") or rt.wizard:
            raise ValueError("Valid live camera and projector calibration are required")
        p=physical_point(cal,req.xy)
        rt.wizard={"index":-1,"kind":"physical","point":p,"key":new_id(),"shown":False,"expected":req.xy,"calibration":cal["id"]}
        return rt.wizard

    @app.post("/api/v1/calibration/physical-report")
    async def physical_report(req:ReferenceReport,rt=Depends(authorize)):
        w=rt.wizard
        cal = rt.current_calibration()
        if mode!="live" or not w or w.get("kind")!="physical" or w["key"]!=req.key or not w["shown"] or not cal or w["calibration"]!=cal["id"]:
            raise ValueError("No matching physical cross has been displayed")
        frame,sig=rt.camera.calibration_frame()
        moved = (rt.objects.drifted_workspace == cal["workspace_id"] if "workspace_id" in cal else
                 rt.tracker.drift or not frame or any(k not in frame[1] for k in range(4)))
        if not frame or moved or geometry_reason(cal,sig,rt.display(),rt.topology):
            raise ValueError("Calibration changed; discard this reference measurement")
        if any(v<-.5 or v>b+.5 for v,b in zip(req.xy,cal["wall"])):
            raise ValueError("Enter measured wall coordinates in meters")
        evidence={"time":time.time(),"provenance":"operator_ruler_measurement","expected":w["expected"],
                  "measured":req.xy,**residuals(w["expected"],req.xy)}
        rt.store.add_reference(cal["id"],evidence)
        rt.clear_wizard()
        return evidence

    @app.get("/api/v1/calibration/diagnostics")
    async def diagnostics(rt=Depends(authorize)):
        stability=[]
        if mode=="live":
            for marker,frames in sorted(rt.stability.items()):
                recent=[(x,y) for t,x,y in frames if time.time()-t<8]
                if len(recent)<10:
                    continue
                pts=np.asarray(recent)
                radial=np.linalg.norm(pts-np.median(pts,axis=0),axis=1)*1000
                stability.append({"marker":marker,"frames":len(pts),"p50_mm":float(np.percentile(radial,50)),"p95_mm":float(np.percentile(radial,95))})
        cal = rt.current_calibration()
        return {"software_latency":rt.timing.summary() if mode=="live" else Timing().summary(),"stability":stability,
                "physical":rt.store.references(cal["id"]) if mode=="live" and cal else []}

    @app.post("/api/v1/demo/replay")
    async def replay(rt=Depends(authorize)):
        if mode!="demo":
            raise ValueError("Fixture replay is available only in demo mode")
        rt.replay_start=time.time()
        return {"mode":"demo"}

    @app.get("/api/v1/commits")
    def history(rt=Depends(authorize)):
        return rt.store.list()

    @app.get("/api/v1/scenes/{scene_id}")
    def scene(scene_id:Id,rt=Depends(authorize)):
        data=rt.store.list()
        current=next(c["scene"] for c in data["commits"] if c["id"]==data["branches"]["main"])
        if scene_id!=current["id"]:
            raise HTTPException(404,"Scene does not exist")
        return current

    @app.post("/api/v1/commits")
    async def commit(req:Save,rt=Depends(authorize)):
        scene=req.scene
        evidence=None
        if req.observed:
            live=rt.last
            if not live or live["state"] in ("DISCONNECTED","CALIBRATION_DRIFT") or not rt.cal or time.time()-live["timestamp"]>.6:
                raise ValueError("A current calibrated observation is required")
            if not scene:
                raise ValueError("Register the object markers and dimensions in the 3D editor first")
            poses={p["marker"]:p for p in rt.poses if p["confidence"]>=.65}
            if not scene.objects or any(o.marker not in poses for o in scene.objects):
                raise ValueError("Every registered object must be clearly visible")
            scene=scene.model_copy(update={"objects":[o.model_copy(update={k:poses[o.marker][k] for k in ("x","y","angle")})
                                                     for o in scene.objects],"wall":rt.cal["wall"]})
            evidence=dict(mode=mode,seq=live["seq"],calibration=rt.cal["id"])
        if not scene:
            raise ValueError("A scene is required")
        return rt.store.save(req.branch,req.expected,scene,req.message,evidence)

    @app.post("/api/v1/branches")
    def branch(req:Branch,rt=Depends(authorize)):
        rt.store.branch(req.name,req.commit)
        return rt.store.list()

    @app.post("/api/v1/diff")
    def diff(req:Diff,rt=Depends(authorize)):
        return rt.store.compare(req.before,req.after)

    @app.post("/api/v1/merge")
    def merge(req:Merge,rt=Depends(authorize)):
        return rt.store.merge(req)

    @app.post("/api/v1/deployments")
    async def deploy(req:Deploy,rt=Depends(authorize)):
        rt.require_idle_calibration()
        cal = rt.current_calibration()
        if not cal or not cal.get("wall_to_projector") or cal.get("units", "m") != "m" or not rt.last or rt.last["state"] in ("SETUP_REQUIRED","CALIBRATION_DRIFT","DISCONNECTED"):
            raise ValueError("Connect and validate your hardware before restoring")
        with rt.store.tx() as db:
            revision=rt.store.commit(db,req.commit)
        scene=Scene.model_validate(revision["scene"])
        objects=[o for o in scene.objects if not req.object_id or o.id==req.object_id]
        if not objects or issues(scene) or not np.allclose(scene.wall,cal["wall"],atol=.002,rtol=0):
            raise ValueError("Revision targets or wall dimensions do not match the calibrated wall")
        if any(np.any((p:=mapped(cal["wall_to_projector"],corners(o)))<0) or np.any(p>=cal["output"]) for o in objects):
            raise ValueError("At least one target is outside the calibrated projector output")
        rt.plan=Plan(revision,objects,mode,req.tolerance_mm,req.dwell_s)
        rt.plan.calibration_id=cal["id"]
        rt.store.save_plan(rt.plan,list(scene.wall))
        return {"id":rt.plan.id}

    @app.post("/api/v1/deployments/active/confirm")
    async def confirm_restore(rt=Depends(authorize)):
        plan, cal = rt.plan, rt.current_calibration()
        if (not plan or not cal or not rt.last or rt.last["state"] != "VERIFIED"
                or not plan.completed or cal["id"] != plan.calibration_id):
            raise ValueError("Complete the physical restore before saving it")
        tracked = rt.objects.snapshot(cal, time.time()) if "workspace_id" in cal else rt.poses
        stamp = min((p.get("timestamp", rt.last["timestamp"]) for p in tracked), default=0)
        if time.time() - stamp > .35:
            raise ValueError("The verified objects must still be visible")
        plan.saved = rt.store.save_verified(plan, tracked, cal["id"], rt.last["seq"], stamp)
        return {"revision":plan.saved}

    @app.get("/api/v1/deployments/{plan}")
    def evidence(plan:Id,rt=Depends(authorize)):
        return rt.store.evidence(plan)

    @app.delete("/api/v1/deployments/active")
    async def cancel(rt=Depends(authorize)):
        rt.plan=None
        return {"status":"stopped"}

    @app.websocket("/ws/live")
    async def live(ws:WebSocket):
        if ws.headers.get("origin") not in origins[:2] or "spacegit.v1" not in ws.scope.get("subprotocols",[]):
            await ws.close(code=1008)
            return
        await ws.accept(subprotocol="spacegit.v1")
        try:
            supplied=await asyncio.wait_for(ws.receive_text(),3)
            if not operator(supplied, ws.headers.get("origin", "")):
                await ws.close(code=1008)
                return
            while True:
                await ws.send_json(runtime().last)
                await asyncio.sleep(.04)
        except (WebSocketDisconnect, asyncio.TimeoutError, OSError):
            with suppress(RuntimeError):
                await ws.close()

    @app.post("/api/v1/capture/pair/{commit}")
    async def pair(commit:Id,rt=Depends(authorize)):
        if not mobile:
            raise ValueError("Configure the HTTPS mobile origin on the local edge first")
        rt.pairings={k:v for k,v in rt.pairings.items() if v[1]>time.time()}
        if len(rt.pairings)>=20:
            raise ValueError("Too many active capture links")
        key=secrets.token_urlsafe(32)
        session=new_capture(rt,commit,"paired-phone")
        rt.pairings[key]=(commit,time.time()+600,session["id"])
        return {"url":f"{mobile}/studio/capture/#pair={key}","expires_s":600,"session":session["id"]}

    @app.post("/api/v1/capture/sessions/{commit}")
    def create_capture(commit:Id,rt=Depends(authorize)):
        return new_capture(rt,commit,"operator")

    @app.get("/api/v1/capture/sessions")
    def captures(rt=Depends(authorize)):
        with rt.store.tx() as db:
            return [capture_summary(db,r[0]) for r in db.execute("SELECT id FROM capture_sessions ORDER BY created DESC LIMIT 60")]

    @app.get("/api/v1/capture/paired")
    def paired(request:Request,authorization:str=Header(default="")):
        rt=runtime()
        _,expiry,ident=mobile_lease(rt,authorization,request.headers.get("origin",""))
        with rt.store.tx() as db:
            s=capture_summary(db,ident)
        return {"count":s["count"],"request_quality":s["request_quality"],"expires_s":max(0,int(expiry-time.time()))}

    @app.post("/api/v1/capture/paired/request")
    def request_reconstruction(req:CaptureRequest,request:Request,authorization:str=Header(default="")):
        rt=runtime()
        _,_,ident=mobile_lease(rt,authorization,request.headers.get("origin",""))
        with rt.store.tx(True) as db:
            s=capture_summary(db,ident)
            if s["count"]<6:
                raise ValueError("Add at least six overlapping photos to this session")
            db.execute("UPDATE capture_sessions SET request_quality=? WHERE id=?",(req.quality,ident))
        return {"status":"requested","quality":req.quality}

    @app.post("/api/v1/capture/photos")
    async def photo(request:Request,authorization:str=Header(default="")):
        rt=runtime()
        origin=request.headers.get("origin","")
        commit=session=None
        if secrets.compare_digest(authorization.encode(),f"Bearer {token}".encode()) and origin in ["",*origins[:2]]:
            pass
        else:
            commit,_,session=mobile_lease(rt,authorization,origin)
        if request.headers.get("content-length","0").isdigit() and int(request.headers.get("content-length","0"))>16*1024*1024:
            raise HTTPException(413,"Photo exceeds 15 MB")
        async with request.form(max_files=1,max_fields=2,max_part_size=1024) as form:
            commit=commit or form.get("commit")
            if not isinstance(commit,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",commit):
                raise HTTPException(422,"Select a valid revision")
            image=form.get("image")
            session=session or form.get("session")
            if session is not None and (not isinstance(session,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",session)):
                raise HTTPException(422,"Invalid capture session")
            if not isinstance(image,UploadFile):
                raise HTTPException(422,"Choose a JPEG or PNG photo")
            raw=await image.read(15*1024*1024+1)
        if len(raw)>15*1024*1024:
            raise HTTPException(413,"Photo exceeds 15 MB")
        try:
            with Image.open(BytesIO(raw)) as im:
                if im.format not in ("JPEG","PNG") or im.width*im.height>32_000_000:
                    raise HTTPException(422,"Choose a JPEG or PNG photo under 32 megapixels")
                ext,mime=("jpg","image/jpeg") if im.format=="JPEG" else ("png","image/png")
                exif=Image.Exif()
                if raw_exif:=im.info.get("exif"):
                    exif.load(raw_exif)
                orientation=exif.get(274,1)
                if not isinstance(orientation,int) or not 1<=orientation<=8:
                    orientation=1
                info={"resolution":[im.width,im.height],"display_resolution":[im.height,im.width] if orientation>=5 else [im.width,im.height],
                      "orientation":orientation,"device":photo_device(request.headers.get("user-agent","")),"bytes":len(raw),"time":time.time()}
                im.verify()
        except (UnidentifiedImageError,OSError,SyntaxError,Image.DecompressionBombError):
            raise HTTPException(422,"Choose a valid JPEG or PNG photo")
        digest=hashlib.sha256(raw).hexdigest()
        with rt.store.tx(True) as db:
            rt.store.commit(db,commit)
            old=db.execute("SELECT id FROM photos WHERE commit_id=? AND digest=?",(commit,digest)).fetchone()
            fid=old[0] if old else new_id()
            if session:
                capture=capture_summary(db,session)
                if capture["commit"]!=commit:
                    raise ValueError("Capture session belongs to a different revision")
                if capture["count"]>=80 and fid not in capture["photos"]:
                    raise ValueError("Capture session is full (80 photos)")
            if not old:
                (files/"photos").mkdir(parents=True,exist_ok=True)
                (files/"photos"/f"{fid}.{ext}").write_bytes(raw)
                db.execute("INSERT INTO photos VALUES(?,?,?,?)",(fid,commit,mime,digest))
                db.execute("INSERT INTO photo_metadata VALUES(?,?)",(fid,compact(info)))
            if session:
                db.execute("INSERT OR IGNORE INTO capture_entries VALUES(?,?)",(session,fid))
        return {"id":fid,"commit":commit,"session":session,"metadata":info}

    @app.get("/api/v1/capture/photos")
    def photos(rt=Depends(authorize)):
        with rt.store.tx() as db:
            return [{"id":i,"commit":c,"metadata":json.loads(raw) if raw else None} for i,c,raw in db.execute(
                "SELECT p.id,p.commit_id,m.body FROM photos p LEFT JOIN photo_metadata m ON p.id=m.id ORDER BY p.rowid DESC")]

    @app.delete("/api/v1/capture/photos/{photo_id}")
    def delete_photo(photo_id:Id,rt=Depends(authorize)):
        with rt.store.tx(True) as db:
            row=db.execute("SELECT mime FROM photos WHERE id=?",(photo_id,)).fetchone()
            if not row:
                raise HTTPException(404,"Photo not found")
            if any(photo_id in json.loads(r[0])["photos"] for r in db.execute("SELECT body FROM jobs WHERE stage NOT IN ('complete','partial','failed','cancelled')")):
                raise ValueError("Photo is used by a pending reconstruction")
            ext="jpg" if row[0]=="image/jpeg" else "png"
            (files/"photos"/f"{photo_id}.{ext}").unlink(missing_ok=True)
            db.execute("DELETE FROM photos WHERE id=?",(photo_id,))
        return {"deleted":photo_id}

    @app.post("/api/v1/reconstructions")
    def queue(req:JobInput,rt=Depends(authorize)):
        job=dict(id=new_id(),stage="queued",message="Waiting for the local worker",logs=[],asset=None,photos=req.photos,
                 count=len(req.photos),time=time.time(),quality=req.quality,artifacts=[])
        with rt.store.tx(True) as db:
            if len(set(req.photos))!=len(req.photos):
                raise ValueError("Choose distinct photos")
            refs=[db.execute("SELECT commit_id,digest FROM photos WHERE id=?",(p,)).fetchone() for p in req.photos]
            if any(p is None for p in refs) or len({p[0] for p in refs})!=1 or len({p[1] for p in refs})!=len(refs):
                raise ValueError("Choose unique photographs from the same revision")
            job["commit"]=refs[0][0]
            db.execute("INSERT INTO jobs VALUES(?,?,?)",(job["id"],job["stage"],compact(job)))
        return job

    @app.get("/api/v1/reconstructions")
    def jobs(rt=Depends(authorize)):
        with rt.store.tx() as db:
            rows=[json.loads(r[0]) for r in db.execute("SELECT body FROM jobs ORDER BY rowid DESC")]
        return {"jobs":rows,"colmap":bool(shutil.which(os.getenv("SPACEGIT_COLMAP","colmap")))}

    @app.post("/api/v1/reconstructions/{job_id}/cancel")
    def cancel_job(job_id:Id,rt=Depends(authorize)):
        with rt.store.tx(True) as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Reconstruction job not found")
            job = json.loads(row[0])
            if job["stage"] == "queued":
                job.update(stage="cancelled", message="Cancelled before the worker started.")
            elif job["stage"] not in ("complete", "partial", "failed", "cancelled"):
                job.update(cancel_requested=True, message="Waiting for the worker to stop.")
            db.execute("UPDATE jobs SET stage=?,body=? WHERE id=?", (job["stage"], compact(job), job_id))
        return job

    @app.post("/api/v1/reconstructions/{job_id}/retry")
    def retry_job(job_id:Id,rt=Depends(authorize)):
        with rt.store.tx() as db:
            row = db.execute("SELECT body FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Reconstruction job not found")
        job = json.loads(row[0])
        if job["stage"] not in ("partial", "failed", "cancelled"):
            raise ValueError("Only failed, partial, or cancelled jobs can be retried")
        return queue(JobInput(photos=job["photos"], quality=job.get("quality", "sparse")), rt)

    @app.get("/api/v1/assets/{asset}/placement/{commit}")
    def get_placement(asset:Id,commit:Id,rt=Depends(authorize)):
        with rt.store.tx() as db:
            job=registered_job(db,asset)
            if job["commit"]!=commit:
                raise HTTPException(404,"Asset belongs to a different revision")
            row=db.execute("SELECT body FROM visual_placements WHERE asset=? AND revision=?",(asset,commit)).fetchone()
        return json.loads(row[0]) if row else VisualTransform(commit=commit).model_dump()

    @app.post("/api/v1/assets/{asset}/placement")
    def place_asset(asset:Id,req:VisualTransform,rt=Depends(authorize)):
        with rt.store.tx(True) as db:
            job=registered_job(db,asset)
            if job["commit"]!=req.commit or "model.glb" not in {a["name"] for a in job.get("artifacts",[])}:
                raise HTTPException(404,"A mesh asset attached to this revision is required")
            body=req.model_dump(mode="json")
            db.execute("INSERT OR REPLACE INTO visual_placements VALUES(?,?,?)",(asset,req.commit,compact(body)))
        return body

    @app.get("/api/v1/assets/{asset}/{name}")
    @app.get("/api/v1/assets/{asset}")
    def get_asset(asset:Id,name:str="sparse.ply",rt=Depends(authorize)):
        with rt.store.tx() as db:
            body=registered_job(db,asset)
        names={a["name"] for a in body.get("artifacts",[])} or {"sparse.ply"}
        if name not in ARTIFACTS or name not in names:
            raise HTTPException(404,"Registered asset is unavailable")
        result=files/"jobs"/asset/name
        if not result.is_file():
            raise HTTPException(404,"Registered asset is unavailable")
        return FileResponse(result,media_type=ARTIFACTS[name],filename=f"{asset[:8]}-{name}")

    app.include_router(rig_routes(authorize))
    return app


app=make_app()

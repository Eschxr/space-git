"""Independently acquire the four views on a single pole; no camera fusion."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field, StrictInt, model_validator

from .camera import Camera
from .models import CameraInput, Id, Strict
from .store import new_id

SLOTS = (1, 2, 3, 4)
EXPORT_NAMES = {1: "01_radial_a.jpg", 2: "02_radial_b.jpg", 3: "03_radial_c.jpg", 4: "04_floor.jpg"}
POINTDIT_OUTPUT = Path(r"\\wsl.localhost\Ubuntu\home\wilson\pointdit\generation\pretrained-pointditl-512-mixdata-nodinov3-240c1a4f\test_images")


def pointdit_output():
    return Path(os.environ.get("SPACEGIT_POINTDIT_OUTPUT_DIR") or POINTDIT_OUTPUT)
DeviceIndex = Annotated[StrictInt, Field(ge=0, le=15)]
Source = DeviceIndex | Literal["primary"] | None


class RigSettings(Strict):
    sources: tuple[Source, Source, Source, Source]
    order: tuple[StrictInt, StrictInt, StrictInt, StrictInt] = SLOTS

    @model_validator(mode="after")
    def validate_sequence(self):
        assigned = [source for source in self.sources if source is not None]
        if len(assigned) != len(set(assigned)):
            raise ValueError("Assign each device to only one camera position")
        if set(self.order) != set(SLOTS):
            raise ValueError("Use each camera position once in the sequence")
        return self


def camera_mapping(raw):
    slots = [value.strip() for value in raw.split(",")]
    if len(slots) != 4 or any(value not in ("", "-", "primary") and
                             (not value.isascii() or not value.isdecimal() or len(value) > 2 or int(value) > 15)
                             for value in slots):
        raise ValueError("SPACEGIT_RIG_CAMERAS needs four comma-separated values: primary, index (0-15), or -")
    mapping = [None if value in ("", "-") else value if value == "primary" else int(value) for value in slots]
    active = [value for value in mapping if value is not None]
    if len(set(active)) != len(active):
        raise ValueError("Assign each camera to at most one rig position")
    return dict(zip(SLOTS, mapping))


class PoleRig:
    def __init__(self, primary, store, mode):
        self.primary, self.store, self.mode = primary, store, mode
        saved = store.setting("pole_rig") if mode == "live" else None
        if saved is not None:
            self.settings = RigSettings.model_validate(saved)
        elif mode == "live":
            mapping = camera_mapping(os.getenv("SPACEGIT_RIG_CAMERAS", "primary,-,-,-"))
            self.settings = RigSettings(sources=tuple(mapping.values()))
        else:
            self.settings = RigSettings(sources=(None, None, None, None))
        self.cameras = {index: Camera() for index in self.settings.sources if isinstance(index, int)}
        self.enabled = False
        self.lock = asyncio.Lock()
        self.capture_lock = asyncio.Lock()
        self.output_lock = asyncio.Lock()
        self.export_directory = os.getenv("SPACEGIT_CAPTURE_EXPORT_DIR") if mode == "live" else None
        self.generate_ply = mode == "live" and os.getenv("SPACEGIT_POINTDIT_WSL") == "1"

    def stop(self):
        self.enabled = False
        if self.cameras:
            with ThreadPoolExecutor(max_workers=len(self.cameras)) as pool:
                list(pool.map(Camera.stop, self.cameras.values()))

    def source(self, slot):
        index = self.settings.sources[slot - 1]
        if index == "primary":
            return self.primary
        if self.enabled:
            return self.cameras.get(index)
        return None

    def frame(self, slot):
        camera = self.source(slot)
        value = camera.frame() if camera else None
        return value if value and value[2] else None

    def status(self):
        feeds = []
        for slot in SLOTS:
            camera, value = self.source(slot), self.frame(slot)
            if self.mode == "demo":
                state = "simulated"
            elif self.settings.sources[slot - 1] is None:
                state = "unmapped"
            elif value:
                state = "live"
            elif camera and camera.error in (None, "Opening camera"):
                state = "waiting"
            else:
                state = "offline"
            feeds.append(dict(id=slot, status=state, age_ms=round(max(0, time.time()-value[0])*1000) if value else None,
                              error=camera.error if camera and not value else None))
        return dict(mode=self.mode, enabled=self.enabled, feeds=feeds, settings=self.settings.model_dump(mode="json"))

    def require_live(self):
        if self.mode != "live":
            raise HTTPException(409, "Start the edge in live mode to use rig cameras")

    def check_tracking_camera(self, settings):
        if self.primary.device_index in settings.sources and self.primary.device_index is not None:
            raise HTTPException(409, "The tracking camera is already open. Map that direction to primary.")

    def start(self):
        self.require_live()
        self.check_tracking_camera(self.settings)
        if all(source is None for source in self.settings.sources):
            raise HTTPException(409, "Assign a camera before opening the rig")
        for index, camera in self.cameras.items():
            camera.start(CameraInput(index=index, width=640, height=360))
        self.enabled = True

    def configure(self, settings):
        self.require_live()
        if self.enabled:
            self.check_tracking_camera(settings)
        self.store.setting("pole_rig", settings.model_dump(mode="json"))
        cameras = {}
        for index in settings.sources:
            if isinstance(index, int):
                cameras[index] = self.cameras.get(index) or Camera()
        for index, camera in self.cameras.items():
            if index not in cameras:
                camera.stop()
        if self.enabled:
            for index, camera in cameras.items():
                if index not in self.cameras:
                    camera.start(CameraInput(index=index, width=640, height=360))
        self.cameras = cameras
        self.settings = settings
        if all(source is None for source in settings.sources):
            self.enabled = False


def export_frames(directory, frames):
    """Publish only this session, keeping the previous directory on write failure."""
    target = Path(directory)
    if not target.is_absolute() or target.name in ("", ".", "..") or target.is_symlink() or target.is_junction():
        raise ValueError("Capture export needs an absolute directory path without a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    target = target.parent.resolve(strict=True) / target.name
    if target.exists() and not target.is_dir():
        raise ValueError("Capture export destination must be a directory")
    staging = Path(tempfile.mkdtemp(prefix=".spacegit-capture-", dir=target.parent))
    backup = target.parent / (".spacegit-previous-" + new_id())
    try:
        for slot in SLOTS:
            if slot in frames:
                (staging / EXPORT_NAMES[slot]).write_bytes(frames[slot][2])
        had_previous = target.exists()
        if had_previous:
            target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            if had_previous:
                backup.rename(target)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if backup.exists():
        shutil.rmtree(backup)


def generate_pointdit(log_path):
    outputs = [pointdit_output() / (Path(name).stem + "_pointcloud.ply") for name in EXPORT_NAMES.values()]
    previous = {path: path.stat().st_mtime_ns if path.exists() else None for path in outputs}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "-u", "wilson", "--", "bash", "-lc",
             "cd /home/wilson/pointdit && source .venv/bin/activate && timeout --kill-after=10s 1800s bash scripts/demo_l_512.sh"],
            stdout=log, stderr=subprocess.STDOUT, timeout=1830, check=False,
        )
    if result.returncode:
        raise RuntimeError(f"PointDiT exited with code {result.returncode}. See {log_path}")
    for path in outputs:
        if not path.is_file() or path.stat().st_mtime_ns == previous[path]:
            raise RuntimeError(f"PointDiT did not update {path}. See {log_path}")
        with path.open("rb") as ply:
            if ply.readline().strip() != b"ply":
                raise RuntimeError(f"PointDiT produced an invalid PLY: {path}. See {log_path}")
    return [str(path) for path in outputs]


def routes(authorize):
    router = APIRouter(prefix="/api/v1/rig")

    @router.get("")
    async def rig(rt=Depends(authorize)):
        async with rt.pole.lock:
            return rt.pole.status()

    @router.post("/settings")
    async def save_settings(settings: RigSettings, rt=Depends(authorize)):
        async with rt.pole.lock:
            await asyncio.to_thread(rt.pole.configure, settings)
            return rt.pole.status()

    @router.post("/start")
    async def start(rt=Depends(authorize)):
        async with rt.pole.lock:
            if not rt.pole.enabled:
                await asyncio.to_thread(rt.pole.start)
            return rt.pole.status()

    @router.post("/stop")
    async def stop(rt=Depends(authorize)):
        async with rt.pole.lock:
            await asyncio.to_thread(rt.pole.stop)
            return rt.pole.status()

    @router.get("/frames/{slot}")
    async def preview(slot: int, rt=Depends(authorize)):
        if not rt.pole.lock.locked() and slot in SLOTS and (frame := rt.pole.frame(slot)):
            return Response(frame[2], media_type="image/jpeg")
        raise HTTPException(404, "This camera has no fresh frame")

    @router.get("/captures")
    def captures(rt=Depends(authorize)):
        with rt.store.tx() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM pole_captures ORDER BY rowid DESC LIMIT 50")]

    @router.get("/pointclouds/{slot}")
    async def pointcloud(slot: int, rt=Depends(authorize)):
        rt.pole.require_live()
        if slot not in SLOTS:
            raise HTTPException(404, "Unknown camera position")
        if rt.pole.capture_lock.locked():
            raise HTTPException(409, "Wait for the current capture and PLY generation to finish")
        async with rt.pole.output_lock:
            path = pointdit_output() / (Path(EXPORT_NAMES[slot]).stem + "_pointcloud.ply")
            try:
                data = await asyncio.to_thread(path.read_bytes)
            except FileNotFoundError as error:
                raise HTTPException(404, "Capture four images and generate the PLY files first") from error
            except OSError as error:
                raise HTTPException(503, "Could not read the WSL PointDiT output folder") from error
            return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})

    def save_capture(rt, order, frames):
        if not frames:
            raise HTTPException(409, "No fresh rig frames are available")
        if rt.pole.generate_ply and (set(frames) != set(SLOTS) or not rt.pole.export_directory):
            raise HTTPException(409, "PointDiT needs all four fresh views and an image export directory. Start every camera and capture again.")
        if rt.pole.generate_ply and Path(rt.pole.export_directory) != Path(r"\\wsl.localhost\Ubuntu\home\wilson\test_images"):
            raise HTTPException(409, "The PointDiT script reads /home/wilson/test_images. Set CaptureDirectory to \\\\wsl.localhost\\Ubuntu\\home\\wilson\\test_images.")
        ident = new_id()
        with rt.store.tx(True) as db:
            info = dict(id=ident, created=time.time(), mode="live", feeds=list(frames), order=order,
                        frame_times={slot: frame[0] for slot, frame in frames.items()}, head=rt.store.branches(db).get("main"))
            db.execute("INSERT INTO pole_captures VALUES(?,?)", (ident, json.dumps(info)))
            for slot, frame in frames.items():
                db.execute("INSERT INTO pole_frames VALUES(?,?,?)", (ident, slot, frame[2]))
        if rt.pole.export_directory:
            try:
                export_frames(rt.pole.export_directory, frames)
            except (OSError, ValueError) as error:
                raise HTTPException(503, f"Session saved locally, but image export failed: {error}") from error
        if rt.pole.generate_ply:
            log_path = rt.store.path.parent / "pointdit" / (ident + ".log")
            try:
                files = generate_pointdit(log_path)
                info["pointdit"] = dict(status="succeeded", files=files, log=str(log_path))
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                info["pointdit"] = dict(status="failed", error=str(error), log=str(log_path))
                with rt.store.tx(True) as db:
                    db.execute("UPDATE pole_captures SET body=? WHERE id=?", (json.dumps(info), ident))
                raise HTTPException(503, f"Images saved, but PLY generation failed: {error}") from error
            with rt.store.tx(True) as db:
                db.execute("UPDATE pole_captures SET body=? WHERE id=?", (json.dumps(info), ident))
        return info

    @router.post("/captures", status_code=201)
    async def capture(rt=Depends(authorize)):
        if rt.pole.capture_lock.locked():
            raise HTTPException(409, "A capture is already exporting or generating PLY files. Wait for it to finish.")
        async with rt.pole.capture_lock:
            async with rt.pole.lock:
                order = rt.pole.settings.order
                frames = {slot: frame for slot in order if (frame := rt.pole.frame(slot))}
            async with rt.pole.output_lock:
                return await asyncio.to_thread(save_capture, rt, order, frames)

    @router.get("/captures/{ident}/frames/{slot}")
    def saved_frame(ident: Id, slot: int, rt=Depends(authorize)):
        with rt.store.tx() as db:
            row = db.execute("SELECT jpeg FROM pole_frames WHERE capture=? AND slot=?", (ident, slot)).fetchone()
        if not row:
            raise HTTPException(404, "No frame was captured for this camera")
        return Response(row[0], media_type="image/jpeg")

    return router

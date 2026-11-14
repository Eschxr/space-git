"""Independently acquire the four views on a single pole; no camera fusion."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field, StrictInt, model_validator

from .camera import Camera
from .models import CameraInput, Id, Strict
from .store import new_id

SLOTS = (1, 2, 3, 4)
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

    def save_capture(rt, order, frames):
        if not frames:
            raise HTTPException(409, "No fresh rig frames are available")
        ident = new_id()
        with rt.store.tx(True) as db:
            info = dict(id=ident, created=time.time(), mode="live", feeds=list(frames), order=order,
                        frame_times={slot: frame[0] for slot, frame in frames.items()}, head=rt.store.branches(db).get("main"))
            db.execute("INSERT INTO pole_captures VALUES(?,?)", (ident, json.dumps(info)))
            for slot, frame in frames.items():
                db.execute("INSERT INTO pole_frames VALUES(?,?,?)", (ident, slot, frame[2]))
        return info

    @router.post("/captures", status_code=201)
    async def capture(rt=Depends(authorize)):
        async with rt.pole.lock:
            order = rt.pole.settings.order
            frames = {slot: frame for slot in order if (frame := rt.pole.frame(slot))}
        return await asyncio.to_thread(save_capture, rt, order, frames)

    @router.get("/captures/{ident}/frames/{slot}")
    def saved_frame(ident: Id, slot: int, rt=Depends(authorize)):
        with rt.store.tx() as db:
            row = db.execute("SELECT jpeg FROM pole_frames WHERE capture=? AND slot=?", (ident, slot)).fetchone()
        if not row:
            raise HTTPException(404, "No frame was captured for this camera")
        return Response(row[0], media_type="image/jpeg")

    return router

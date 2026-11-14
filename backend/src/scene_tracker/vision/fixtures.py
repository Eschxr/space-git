"""Synthetic scenarios are explicit fixture instructions, never inferred scene truth."""

import io
import json
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, PngImagePlugin
from pydantic import Field, model_validator

from scene_tracker.domain.contracts import Contract
from scene_tracker.domain.enums import CameraID

METADATA_KEY = "scene_tracker_fixture"


class FixtureObject(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=80)
    box_xyxy: tuple[int, int, int, int]
    appearance_seed: str = Field(min_length=1, max_length=128)


class FixtureScenario(Contract):
    schema_version: Literal[1] = 1
    camera_id: CameraID
    objects: tuple[FixtureObject, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({o.id for o in self.objects}) != len(self.objects):
            raise ValueError("duplicate fixture IDs")
        return self


def synthetic_image(camera: CameraID, *, empty=False, moved=False) -> bytes:
    image = Image.new("RGB", (320, 240), "#e8e4db")
    draw = ImageDraw.Draw(image)
    objects = (
        ()
        if empty
        else (
            FixtureObject(
                id="chair-a",
                label="chair",
                box_xyxy=(35 + 15 * moved, 60, 125 + 15 * moved, 170),
                appearance_seed=f"{camera}-chair-a",
            ),
            FixtureObject(
                id="box-b",
                label="box",
                box_xyxy=(190, 100, 275, 190),
                appearance_seed=f"{camera}-box-b",
            ),
        )
    )
    scenario = FixtureScenario(camera_id=camera, objects=objects)
    draw.text((10, 10), f"{camera} {camera.role} - SYNTHETIC FIXTURE, NO ML", fill="black")
    for obj, color in zip(objects, ("#6996bd", "#c99560"), strict=False):
        x1, y1, x2, y2 = obj.box_xyxy
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), fill=color)
        draw.text((x1, y1 + 5), obj.id, fill="black")
    info = PngImagePlugin.PngInfo()
    info.add_text(METADATA_KEY, scenario.model_dump_json())
    stream = io.BytesIO()
    image.save(stream, format="PNG", pnginfo=info)
    return stream.getvalue()


def generate_capture(output: Path, *, empty=False, moved=False):
    output.mkdir(parents=True, exist_ok=True)
    for camera in CameraID:
        path = output / f"{camera}.png"
        # Generated fixtures never overwrite existing evidence/files.
        with path.open("xb") as stream:
            stream.write(synthetic_image(camera, empty=empty, moved=moved))
    (output / "scenario.json").write_text(
        json.dumps(
            {"synthetic": True, "empty": empty, "moved": moved, "schema_version": 1}, sort_keys=True
        )
    )

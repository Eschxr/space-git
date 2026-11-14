import io
from dataclasses import replace

from PIL import Image, ImageOps

from scene_tracker.vision.fixtures import METADATA_KEY, FixtureScenario


def load_frame(store, frame):
    stored = store.stat(frame["storage_key"])
    raw = store.get(replace(stored, sha256=frame["sha256"], content_type=frame["content_type"]))
    with Image.open(io.BytesIO(raw)) as image:
        metadata = image.info.get(METADATA_KEY)
        rgb = ImageOps.exif_transpose(image).convert("RGB")
    if rgb.size != (frame["width"], frame["height"]):
        raise ValueError("oriented frame dimensions mismatch")
    scenario = (
        FixtureScenario.model_validate_json(metadata)
        if metadata
        else FixtureScenario(camera_id=frame["camera_id"])
    )
    if scenario.camera_id != frame["camera_id"]:
        raise ValueError("fixture camera role mismatch")
    return rgb, scenario, (() if metadata else ("no fixture metadata: fake output is empty",))

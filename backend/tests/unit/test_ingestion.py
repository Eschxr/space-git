import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from PIL import Image

from scene_tracker.application.ingest import ImageUpload, ingest_capture
from scene_tracker.domain.contracts import Capture
from scene_tracker.domain.enums import CameraID
from scene_tracker.infrastructure.storage.base import Blob, checksum
from scene_tracker.infrastructure.storage.local import LocalStore


def uploads(fmt="PNG", orientation=None):
    stream = io.BytesIO()
    image = Image.new("RGB", (12, 8), "red")
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(stream, format=fmt, exif=exif)
    ext, mime = {
        "PNG": ("png", "image/png"),
        "JPEG": ("jpg", "image/jpeg"),
        "WEBP": ("webp", "image/webp"),
    }[fmt]
    return [ImageUpload(c, f"{c}.{ext}", mime, stream.getvalue()) for c in CameraID]


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_original_bytes_and_roles(tmp_path, fmt):
    env = uuid4()
    store = LocalStore(tmp_path, env)
    images = uploads(fmt)
    capture = ingest_capture(env, datetime.now(UTC), images, store)
    assert len(capture.frames) == 4
    assert capture.frames[-1].role == "overhead"
    assert Capture.model_validate_json(capture.model_dump_json()) == capture
    for frame, upload in zip(capture.frames, images, strict=True):
        blob = Blob(frame.storage_key, frame.sha256, frame.content_type, len(upload.data))
        assert store.get(blob) == upload.data
        assert checksum(upload.data) == frame.sha256


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "corrupt",
        "mime",
        "filename",
        "extension",
        "bytes",
        "pixels",
        "naive",
    ],
)
def test_invalid_capture_writes_nothing(tmp_path, case):
    env = uuid4()
    images = uploads()
    kwargs = {}
    if case == "missing":
        images.pop()
    elif case == "duplicate":
        images[-1] = images[0]
    elif case == "corrupt":
        images[-1] = replace(images[-1], data=b"not an image")
    elif case == "mime":
        images[-1] = replace(images[-1], content_type="image/jpeg")
    elif case == "filename":
        images[-1] = replace(images[-1], filename="../cam_04.png")
    elif case == "extension":
        images[-1] = replace(images[-1], filename="cam_04.jpg")
    elif case == "bytes":
        kwargs["max_bytes"] = 1
    elif case == "pixels":
        kwargs["max_pixels"] = 1
    elif case == "naive":
        images[-1] = replace(images[-1], captured_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        ingest_capture(env, datetime.now(UTC), images, LocalStore(tmp_path, env), **kwargs)
    assert not list(tmp_path.rglob("*"))


def test_exif_dimensions_and_timestamp_warning(tmp_path):
    env = uuid4()
    now = datetime.now(UTC)
    images = uploads("JPEG", orientation=6)
    images[-1] = replace(images[-1], captured_at=now + timedelta(seconds=5))
    capture = ingest_capture(env, now, images, LocalStore(tmp_path, env))
    assert capture.warnings
    frame = capture.frames[-1]
    assert (frame.width, frame.height) == (8, 12)
    assert (frame.original_width, frame.original_height, frame.exif_orientation) == (12, 8, 6)
    assert frame.captured_at == images[-1].captured_at


def test_storage_failure_does_not_return_ready(tmp_path):
    class FailingStore(LocalStore):
        def put(self, key, data, content_type):
            super().put(key, data, content_type)
            raise OSError("storage offline")

    env = uuid4()
    with pytest.raises(OSError, match="offline"):
        ingest_capture(env, datetime.now(UTC), uploads(), FailingStore(tmp_path, env))

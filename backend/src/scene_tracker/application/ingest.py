"""Validate a complete capture before writing original received bytes.

Database state transitions/API orchestration belong to Phase 2. A storage failure
raises without returning a ready capture; already written immutable blobs are retained.
"""

import io
import json
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from scene_tracker.domain.contracts import Capture, Frame
from scene_tracker.domain.enums import CameraID, CaptureStatus
from scene_tracker.infrastructure.storage.base import ArtifactStore, checksum


@dataclass(frozen=True)
class ImageUpload:
    camera_id: CameraID
    filename: str
    content_type: str
    data: bytes
    captured_at: datetime | None = None


FORMATS = {
    "JPEG": ("image/jpeg", {".jpg", ".jpeg"}),
    "PNG": ("image/png", {".png"}),
    "WEBP": ("image/webp", {".webp"}),
}


def ingest_capture(
    environment_id: UUID,
    captured_at: datetime,
    uploads: list[ImageUpload],
    store: ArtifactStore,
    *,
    max_bytes: int = 20 * 1024 * 1024,
    max_pixels: int = 40_000_000,
    max_skew_seconds: float = 2,
    capture_id: UUID | None = None,
) -> Capture:
    if max_bytes <= 0 or max_pixels <= 0 or max_skew_seconds < 0:
        raise ValueError("invalid ingestion limits")
    if captured_at.utcoffset() is None:
        raise ValueError("capture timestamp must be timezone aware")
    roles = [CameraID(u.camera_id) for u in uploads]
    if len(roles) != 4 or set(roles) != set(CameraID):
        raise ValueError("exactly four unique camera roles required")
    capture_id = capture_id or uuid4()
    validated = []
    for upload in sorted(uploads, key=lambda u: u.camera_id):
        camera = CameraID(upload.camera_id)
        path = PurePath(upload.filename)
        if path.name != upload.filename or path.stem != camera.value:
            raise ValueError("filename must match canonical camera role")
        if not upload.data or len(upload.data) > max_bytes:
            raise ValueError("image byte limit exceeded or empty image")
        if upload.captured_at is not None and upload.captured_at.utcoffset() is None:
            raise ValueError("frame timestamp must be timezone aware")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(upload.data)) as image:
                    mime, extensions = FORMATS.get(image.format, (None, set()))
                    if mime != upload.content_type or path.suffix.lower() not in extensions:
                        raise ValueError("image signature, extension and MIME must agree")
                    if image.width * image.height > max_pixels:
                        raise ValueError("image pixel limit exceeded")
                    original_width, original_height = image.size
                    image.verify()
                with Image.open(io.BytesIO(upload.data)) as image:
                    orientation = image.getexif().get(274, 1)
                    oriented = ImageOps.exif_transpose(image).convert("RGB")
                    width, height = oriented.size
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ValueError("invalid or unsafe image") from exc
        digest = checksum(upload.data)
        frame = Frame(
            id=uuid4(),
            capture_id=capture_id,
            camera_id=camera,
            storage_key=f"originals/{environment_id}/{capture_id}/{camera}/{digest}{path.suffix.lower()}",
            sha256=digest,
            width=width,
            height=height,
            original_width=original_width,
            original_height=original_height,
            exif_orientation=orientation,
            captured_at=upload.captured_at,
            content_type=mime,
        )
        validated.append((frame, upload.data))
    timestamps = [captured_at] + [f.captured_at for f, _ in validated if f.captured_at]
    skew = (max(timestamps) - min(timestamps)).total_seconds()
    manifest = [
        (f.camera_id.value, f.sha256, f.captured_at.isoformat() if f.captured_at else None)
        for f, _ in validated
    ]
    for frame, data in validated:
        store.put(frame.storage_key, data, frame.content_type)
    return Capture(
        id=capture_id,
        environment_id=environment_id,
        captured_at=captured_at,
        status=CaptureStatus.READY,
        frames=tuple(f for f, _ in validated),
        source_manifest_hash=checksum(json.dumps(manifest, separators=(",", ":")).encode()),
        warnings=(f"frame timestamp skew {skew:g}s exceeds {max_skew_seconds:g}s",)
        if skew > max_skew_seconds
        else (),
    )

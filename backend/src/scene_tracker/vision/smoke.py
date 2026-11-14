"""Manual-only real four-image smoke. No weights or source code are downloaded."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from scene_tracker.application.ingest import ImageUpload, ingest_capture
from scene_tracker.application.vision_pipeline import process_pipeline
from scene_tracker.domain.enums import CameraID
from scene_tracker.infrastructure.storage.local import LocalStore
from scene_tracker.vision.runtime import load_models


class SmokeRepository:
    def __init__(self, output):
        self.output = output
        self.artifacts = []

    def add_artifact(self, environment_id, run_id, ref):
        self.artifacts.append(ref)

    def add_detections(self, records):
        with (self.output / "detections.jsonl").open("a") as stream:
            for record in records:
                stream.write(json.dumps(record, default=str, sort_keys=True) + "\n")

    def progress(self, run_id, value):
        (self.output / "progress.json").write_text(json.dumps(value, sort_keys=True))

    def save_manifest(self, run_id, manifest):
        (self.output / "manifest.json").write_text(json.dumps(manifest, indent=2))


def run_smoke(input_dir, output, settings):
    from scene_tracker.vision.readiness import preflight

    assets = preflight(settings.vision)  # Clear model_unavailable before any output writes.
    uploads = []
    mimes = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    files = [p for p in input_dir.iterdir() if p.suffix.lower() in mimes]
    if len(files) != 4 or {p.stem for p in files} != {c.value for c in CameraID}:
        raise ValueError("input must contain exactly cam_01..cam_04, one supported image per role")
    for path in sorted(files):
        with path.open("rb") as stream:
            data = stream.read(settings.max_image_bytes + 1)
        uploads.append(
            ImageUpload(CameraID(path.stem), path.name, mimes[path.suffix.lower()], data)
        )
    extractor, embedder, provenance = load_models(settings.vision)
    output.mkdir(parents=True, exist_ok=False)
    environment_id, run_id = uuid4(), uuid4()
    store = LocalStore(output / "objects", environment_id)
    capture = ingest_capture(
        environment_id,
        datetime.now(UTC),
        uploads,
        store,
        max_bytes=settings.max_image_bytes,
        max_pixels=settings.max_image_pixels,
    )
    config = {
        "provider": "real",
        "pipeline_version": "real-v1",
        "preset": "default",
        "extractor": "yoloe",
        "assets": assets,
        "vision": settings.vision.model_dump(mode="json"),
    }
    run = {
        "id": run_id,
        "config_hash": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "model_manifest": {"config": config},
    }
    repository = SmokeRepository(output)
    state = {"id": str(run_id), "capture": capture.model_dump(mode="json"), "status": "running"}
    try:
        process_pipeline(
            repository,
            run,
            capture.model_dump(),
            store,
            extractor=extractor,
            embedder=embedder,
            model_provenance=provenance,
        )
        state["status"] = "succeeded"
    except Exception as exc:
        state.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        (output / "run.json").write_text(json.dumps(state, indent=2))
        for ref in repository.artifacts:
            if ref.kind in {"report", "inspection_bundle"}:
                blob = replace(store.stat(ref.key), sha256=ref.sha256)
                (
                    output / ("summary.html" if ref.kind == "report" else "inspection.zip")
                ).write_bytes(store.get(blob))
    return state

"""Camera-ordered fake fixture pipeline. All derivatives are immutable and run-scoped."""

import hashlib
import importlib.metadata
import json
import logging
import sys
import time
from pathlib import Path
from uuid import uuid5

import numpy as np

from scene_tracker.vision.contracts import (
    ArtifactRef,
    FrameContext,
    PerCameraResult,
    ProcessingManifest,
)
from scene_tracker.vision.debug.overlays import overlays, png
from scene_tracker.vision.debug.report import bundle, report
from scene_tracker.vision.detection.fake import FakeDetector
from scene_tracker.vision.embeddings.fake import FakeEmbedder
from scene_tracker.vision.masks import decode_mask
from scene_tracker.vision.preprocessing import load_frame
from scene_tracker.vision.segmentation.fake import FakeSegmenter

logger = logging.getLogger(__name__)


class PipelineFailed(RuntimeError):
    pass


class ArtifactWriter:
    def __init__(self, repository, store, run_id, environment_id):
        self.repository, self.store = repository, store
        self.run_id, self.environment_id = run_id, environment_id
        self.files, self.refs = {}, []

    def put(self, path, data, content_type, kind, camera_id=None):
        blob = self.store.put(f"vision/{self.run_id}/{path}", data, content_type)
        ref = ArtifactRef(
            id=uuid5(self.run_id, path),
            key=blob.key,
            sha256=blob.sha256,
            size=blob.size,
            content_type=content_type,
            camera_id=camera_id,
            kind=kind,
            trace_id=str(self.run_id),
        )
        self.repository.add_artifact(self.environment_id, self.run_id, ref)
        self.files[path] = data
        self.refs.append(ref)
        logger.info("Stored %s", path, extra={"correlation_id": str(self.run_id)})
        return ref

    def json(self, path, value, kind, camera_id=None):
        return self.put(
            path,
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
            "application/json",
            kind,
            camera_id,
        )


def validate_alignment(context, boxes, masks, embeddings):
    ids = [box.id for box in boxes]
    if (
        len(set(ids)) != len(ids)
        or ids != [m.detection_id for m in masks]
        or ids != [e.detection_id for e in embeddings]
    ):
        raise ValueError("adapter detection/mask/embedding alignment mismatch")
    for value in [*boxes, *masks, *embeddings]:
        if any(getattr(value, k) != v for k, v in context.model_dump().items()):
            raise ValueError("adapter frame context mismatch")
    for mask in masks:
        if decode_mask(mask.rle).shape != (context.height, context.width):
            raise ValueError("mask array shape mismatch")


def process_fake(repository, run, capture, store, *, detector=None, segmenter=None, embedder=None):
    if run["model_manifest"]["config"]["provider"] != "fake":
        raise PipelineFailed("real provider cannot use fake pipeline")
    detector, segmenter, embedder = (
        detector or FakeDetector(),
        segmenter or FakeSegmenter(),
        embedder or FakeEmbedder(),
    )
    start = time.perf_counter()
    writer = ArtifactWriter(repository, store, run["id"], capture["environment_id"])
    results, errors, timings = [], [], {}
    for frame in sorted(capture["frames"], key=lambda f: f["camera_id"]):
        context = FrameContext(
            run_id=run["id"],
            frame_id=frame["id"],
            camera_id=frame["camera_id"],
            width=frame["width"],
            height=frame["height"],
            trace_id=str(run["id"]),
        )
        camera_start = time.perf_counter()
        artifact_start = len(writer.refs)
        try:
            rgb, scenario, warnings = load_frame(store, frame)
            config = (context, scenario)
            stage_start = time.perf_counter()
            boxes = detector.detect(rgb, [o.label for o in scenario.objects], config)
            timings[f"{context.camera_id}/detect"] = time.perf_counter() - stage_start
            stage_start = time.perf_counter()
            masks = segmenter.segment(rgb, boxes, config)
            timings[f"{context.camera_id}/segment"] = time.perf_counter() - stage_start
            stage_start = time.perf_counter()
            embeddings = embedder.embed(rgb, masks, boxes, config)
            timings[f"{context.camera_id}/embed"] = time.perf_counter() - stage_start
            validate_alignment(context, boxes, masks, embeddings)
            boxes_image, mask_image, sheet, crops = overlays(rgb, boxes, masks)
            records, crop_index = [], []
            for box, mask, embedding, (_, crop) in zip(
                boxes, masks, embeddings, crops, strict=True
            ):
                mask_ref = writer.json(
                    f"{context.camera_id}/masks/{box.id}.json",
                    mask.rle.model_dump(mode="json"),
                    "mask",
                    context.camera_id,
                )
                embedding_ref = writer.put(
                    f"{context.camera_id}/embeddings/{box.id}.f32",
                    np.asarray(embedding.values, dtype="<f4").tobytes(),
                    "application/octet-stream",
                    "embedding",
                    context.camera_id,
                )
                crop_ref = writer.put(
                    f"debug/{context.camera_id}/crops/{box.id}.png",
                    png(crop),
                    "image/png",
                    "masked_crop",
                    context.camera_id,
                )
                record = dict(
                    id=box.id,
                    run_id=run["id"],
                    frame_id=frame["id"],
                    environment_id=capture["environment_id"],
                    label=box.label,
                    det_score=box.score,
                    box_xyxy=list(box.box_xyxy),
                    mask_key=mask_ref.key,
                    mask_score=mask.score,
                    embedding_key=embedding_ref.key,
                    debug_crop_key=crop_ref.key,
                    embedding_metadata={
                        "dimension": embedding.dimension,
                        "dtype": "float32",
                        "byte_order": "little",
                        "model": embedding.model,
                        "sha256": embedding_ref.sha256,
                        "normalized": True,
                        "synthetic": True,
                    },
                )
                records.append(record)
                crop_index.append(
                    {
                        "detection_id": str(box.id),
                        "crop": crop_ref.model_dump(mode="json"),
                        "mask": mask_ref.model_dump(mode="json"),
                        "embedding": embedding_ref.model_dump(mode="json"),
                    }
                )
            writer.json(
                f"debug/{context.camera_id}/detections.json",
                [box.model_dump(mode="json") for box in boxes],
                "detections",
                context.camera_id,
            )
            writer.json(
                f"debug/{context.camera_id}/crop_index.json",
                crop_index,
                "crop_index",
                context.camera_id,
            )
            for name, image in [
                ("boxes.png", boxes_image),
                ("masks.png", mask_image),
                ("crop_sheet.png", sheet),
            ]:
                writer.put(
                    f"debug/{context.camera_id}/{name}",
                    png(image),
                    "image/png",
                    name,
                    context.camera_id,
                )
            repository.add_detections(records)
            result = PerCameraResult(
                **context.model_dump(),
                status="succeeded",
                detections=tuple(boxes),
                masks=tuple(masks),
                embeddings=tuple(embeddings),
                warnings=warnings,
                artifacts=tuple(writer.refs[artifact_start:]),
            )
        except Exception as exc:
            error = f"{context.camera_id}: {type(exc).__name__}: {exc}"
            errors.append(error)
            result = PerCameraResult(
                **context.model_dump(),
                status="failed",
                error=error,
                artifacts=tuple(writer.refs[artifact_start:]),
            )
        timings[str(context.camera_id)] = time.perf_counter() - camera_start
        writer.json(
            f"debug/{context.camera_id}/result.json",
            result.model_dump(mode="json"),
            "camera_result",
            context.camera_id,
        )
        results.append(result)
        repository.progress(
            run["id"],
            {
                "stage": "fake_fixture_pipeline",
                "completed_cameras": len(results),
                "total_cameras": 4,
                "failed_cameras": len(errors),
            },
        )
    for name, phase in [
        ("temporal_matches", 5),
        ("cross_view_candidates", 6),
        ("change_proposals", 7),
    ]:
        writer.json(
            f"debug/{name}.json", {"implemented": False, "planned_phase": phase, "items": []}, name
        )
    timings["total"] = time.perf_counter() - start
    provenance = {
        "adapters": {
            type(a).__name__: {
                "version": "fake-v1",
                "source_sha256": hashlib.sha256(
                    Path(sys.modules[type(a).__module__].__file__).read_bytes()
                ).hexdigest(),
            }
            for a in (detector, segmenter, embedder)
        },
        "checkpoints": {},
        "device": "cpu",
        "packages": {p: importlib.metadata.version(p) for p in ["numpy", "pillow", "pycocotools"]},
        "scores": "synthetic constants, not calibrated probabilities",
    }
    manifest = ProcessingManifest(
        run_id=run["id"],
        capture_id=capture["id"],
        trace_id=str(run["id"]),
        config=run["model_manifest"]["config"],
        config_hash=run["config_hash"],
        provenance=provenance,
        sources=tuple(
            {
                "frame_id": str(f["id"]),
                "camera_id": str(f["camera_id"]),
                "sha256": f["sha256"],
                "storage_key": f["storage_key"],
            }
            for f in sorted(capture["frames"], key=lambda f: f["camera_id"])
        ),
        preprocessing={
            "orientation": "EXIF transpose",
            "color": "RGB",
            "mask": "COCO compressed RLE",
            "embedding": "fake SHA-256 seed vector; L2 normalized float32, dimension 8",
            "crop": "mask-aware, gray background 127; no resizing",
        },
        cameras=tuple(results),
        artifacts=tuple(writer.refs),
        timing_seconds=timings,
        errors=tuple(errors),
    )
    manifest_data = manifest.model_dump(mode="json")
    # Preserve scheduling provenance from the immutable attempt's initial manifest.
    manifest_data.update(
        {k: run["model_manifest"][k] for k in ("job_id", "attempt") if k in run["model_manifest"]}
    )
    writer.json("debug/manifest.json", manifest_data, "manifest")
    writer.put(
        "debug/summary.html", report(run["id"], results, writer.files), "text/html", "report"
    )
    writer.put("inspection.zip", bundle(writer.files), "application/zip", "inspection_bundle")
    repository.save_manifest(run["id"], manifest_data)
    if errors:
        raise PipelineFailed("; ".join(errors))
    return manifest

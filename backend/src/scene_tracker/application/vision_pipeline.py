"""Camera-ordered extraction, evidence, tracking and changes; immutable run artifacts."""

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
from scene_tracker.vision.detection.extractor_fake import FakeExtractor
from scene_tracker.vision.embeddings.fake import FakeEmbedder
from scene_tracker.vision.masks import decode_mask
from scene_tracker.vision.preprocessing import load_frame

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


def process_fake(repository, run, capture, store, *, extractor=None, embedder=None):
    if run["model_manifest"]["config"]["provider"] != "fake":
        raise PipelineFailed("real provider cannot use fake pipeline")
    return process_pipeline(repository, run, capture, store, extractor=extractor, embedder=embedder)


def process_pipeline(
    repository,
    run,
    capture,
    store,
    *,
    embedder=None,
    model_provenance=None,
    extractor=None,
):
    provider = run["model_manifest"]["config"]["provider"]
    if provider == "real" and (embedder is None or extractor is None):
        raise PipelineFailed("real provider requires concrete adapters; fake fallback is forbidden")
    if provider not in {"fake", "real"}:
        raise PipelineFailed("unsupported vision provider")
    detector_called = False
    extractor = extractor or FakeExtractor()
    embedder = embedder or FakeEmbedder()
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
            rgb, scenario, warnings = load_frame(store, frame, parse_fixture=provider == "fake")
            config = (context, scenario)
            stage_start = time.perf_counter()
            boxes, masks = extractor.extract(rgb, config)
            detector_called = True
            if hasattr(extractor, "last_candidates"):
                writer.json(
                    f"debug/{context.camera_id}/extractor.json",
                    extractor.last_candidates,
                    "extractor_diagnostics",
                    context.camera_id,
                )
            timings[f"{context.camera_id}/extract"] = time.perf_counter() - stage_start
            stage_start = time.perf_counter()
            box_ids = [b.id for b in boxes]
            mask_ids = [m.detection_id for m in masks]
            if len(set(box_ids)) != len(box_ids) or mask_ids != [
                i for i in box_ids if i in mask_ids
            ]:
                raise ValueError("adapter detection/mask alignment mismatch")
            if len(set(mask_ids)) != len(mask_ids):
                raise ValueError("duplicate masks")
            masks_by_id = {m.detection_id: m for m in masks}
            minimum = run["model_manifest"]["config"].get("vision", {}).get("min_mask_pixels", 16)
            eligible = [
                b
                for b in boxes
                if b.id in masks_by_id and int(decode_mask(masks_by_id[b.id].rle).sum()) >= minimum
            ]
            embeddings = embedder.embed(
                rgb, [masks_by_id[b.id] for b in eligible], eligible, config
            )
            validate_alignment(context, eligible, [masks_by_id[b.id] for b in eligible], embeddings)
            embeddings_by_id = {e.detection_id: e for e in embeddings}
            timings[f"{context.camera_id}/embed"] = time.perf_counter() - stage_start
            boxes_image, mask_image, sheet, crops = overlays(rgb, boxes, masks)
            records, crop_index = [], []
            for box, (_, crop) in zip(boxes, crops, strict=True):
                mask, embedding = masks_by_id.get(box.id), embeddings_by_id.get(box.id)
                reason = (
                    "missing_mask"
                    if mask is None
                    else ("small_mask" if embedding is None else None)
                )
                if reason:
                    warnings = (*warnings, f"{box.id}: {reason}; embedding unavailable")
                mask_ref = (
                    writer.json(
                        f"{context.camera_id}/masks/{box.id}.json",
                        mask.rle.model_dump(mode="json"),
                        "mask",
                        context.camera_id,
                    )
                    if mask
                    else None
                )
                embedding_ref = (
                    writer.put(
                        f"{context.camera_id}/embeddings/{box.id}.f32",
                        np.asarray(embedding.values, dtype="<f4").tobytes(),
                        "application/octet-stream",
                        "embedding",
                        context.camera_id,
                    )
                    if embedding
                    else None
                )
                crop_ref = writer.put(
                    f"debug/{context.camera_id}/crops/{box.id}.png",
                    png(crop),
                    "image/png",
                    "masked_crop" if mask else "box_crop",
                    context.camera_id,
                )
                crop_metadata = None
                if embedding and provider == "real":
                    from scene_tracker.vision.embeddings.dinov2 import (
                        crop_metadata as describe_crop,
                    )

                    crop_metadata = describe_crop(
                        rgb,
                        box,
                        run["model_manifest"]["config"].get("vision", {}).get("crop_padding", 0.1),
                    )
                record = dict(
                    id=box.id,
                    run_id=run["id"],
                    frame_id=frame["id"],
                    environment_id=capture["environment_id"],
                    label=box.label,
                    det_score=box.score,
                    box_xyxy=list(box.box_xyxy),
                    mask_key=mask_ref.key if mask_ref else None,
                    mask_score=mask.score if mask else None,
                    embedding_key=embedding_ref.key if embedding_ref else None,
                    debug_crop_key=crop_ref.key,
                    embedding_metadata={
                        "dimension": embedding.dimension,
                        "dtype": "float32",
                        "byte_order": "little",
                        "model": embedding.model,
                        "sha256": embedding_ref.sha256,
                        "normalized": True,
                        "synthetic": provider == "fake",
                        "crop_transform": crop_metadata,
                    }
                    if embedding
                    else {"unavailable_reason": reason},
                )
                records.append(record)
                crop_index.append(
                    {
                        "detection_id": str(box.id),
                        "crop": crop_ref.model_dump(mode="json"),
                        "mask": mask_ref.model_dump(mode="json") if mask_ref else None,
                        "embedding": embedding_ref.model_dump(mode="json")
                        if embedding_ref
                        else None,
                        "unavailable_reason": reason,
                        "embedding_crop_transform": crop_metadata,
                        "image_space": {
                            "width": context.width,
                            "height": context.height,
                            "orientation": "canonical",
                            "origin": "top_left",
                        },
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
                "stage": "real_vision_pipeline" if provider == "real" else "fake_fixture_pipeline",
                "completed_cameras": len(results),
                "total_cameras": 4,
                "failed_cameras": len(errors),
            },
        )
    tracking = None
    changes = None
    if not errors and hasattr(repository, "engine"):
        from scene_tracker.application.association import associate

        tracking = associate(repository, run, capture, store)
        from scene_tracker.application.changes import persist_changes

        changes = persist_changes(repository, run, tracking)
        writer.json("debug/tracking.json", tracking, "tracking")
        for result, frame in zip(
            results, sorted(capture["frames"], key=lambda f: f["camera_id"]), strict=True
        ):
            tracks = {
                s["observation"]["id"]: s["view_track_id"]
                for s in tracking["states"]
                if s["camera_id"] == result.camera_id and s["status"] == "observed"
            }
            rgb, _, _ = load_frame(store, frame, parse_fixture=False)
            from scene_tracker.vision.debug.overlays import change_overlay

            writer.put(
                f"debug/{result.camera_id}/changes.png",
                png(change_overlay(rgb, changes, result.camera_id)),
                "image/png",
                "changes_overlay",
                result.camera_id,
            )
            tracked, _, _, _ = overlays(rgb, result.detections, result.masks, tracks)
            writer.put(
                f"debug/{result.camera_id}/tracks.png",
                png(tracked),
                "image/png",
                "tracks",
                result.camera_id,
            )
        for camera, data in tracking["cameras"].items():
            writer.json(f"debug/{camera}/matches.json", data, "matches", camera)
    for name, phase in [
        ("temporal_matches", 5),
        ("cross_view_candidates", 6),
        ("change_proposals", 7),
    ]:
        writer.json(
            f"debug/{name}.json",
            tracking
            if name == "temporal_matches" and tracking
            else {"implemented": True, "items": changes}
            if name == "change_proposals" and changes is not None
            else {"implemented": False, "planned_phase": phase, "items": []},
            name,
        )
    timings["total"] = time.perf_counter() - start
    provenance = {
        "adapters": {
            type(a).__name__: {
                "version": "fake-v1" if provider == "fake" else "real-v1",
                "source_sha256": hashlib.sha256(
                    Path(sys.modules[type(a).__module__].__file__).read_bytes()
                ).hexdigest(),
            }
            for a in (extractor, embedder)
        },
        "checkpoints": {},
        "device": "cpu",
        "packages": {p: importlib.metadata.version(p) for p in ["numpy", "pillow", "pycocotools"]},
        "scores": "synthetic constants, not calibrated probabilities",
    }
    if model_provenance is not None:
        provenance.update(model_provenance)
    manifest = ProcessingManifest(
        scheduled_at=run["model_manifest"].get("scheduled_at"),
        reference=tracking["reference"] if tracking else None,
        provider=provider,
        inference_performed=provider == "real" and detector_called,
        scope="real_vision_pipeline" if provider == "real" else "synthetic_fixture_pipeline",
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
            "embedding": "fake SHA-256 seed vector; L2 normalized float32, dimension 8"
            if provider == "fake"
            else (
                "DINOv2 ViT-S/14 CLS, 384 dimensions; mask-aware padded square 224 bicubic; "
                "ImageNet RGB mean/std; L2 normalization"
            ),
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
        "debug/summary.html",
        report(run["id"], results, writer.files, provider=provider),
        "text/html",
        "report",
    )
    writer.put("inspection.zip", bundle(writer.files), "application/zip", "inspection_bundle")
    repository.save_manifest(run["id"], manifest_data)
    if errors:
        raise PipelineFailed("; ".join(errors))
    return manifest

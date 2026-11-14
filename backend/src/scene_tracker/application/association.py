"""Run-scoped camera-local tracks; all physical-object links remain untouched."""

from uuid import UUID, uuid5

import numpy as np
from sqlalchemy import case, insert, select, update

from scene_tracker.core.errors import AppError
from scene_tracker.core.tracking_settings import TrackingSettings
from scene_tracker.domain.contracts import Mask
from scene_tracker.infrastructure.db.models import (
    artifacts,
    captures,
    detections,
    environments,
    frames,
    processing_runs,
    revision_track_snapshots,
    revisions,
    track_observations,
    view_track_snapshots,
    view_tracks,
)
from scene_tracker.vision.masks import decode_mask
from scene_tracker.vision.matching.intra_view import match


def observation(row, capture_id):
    return {
        "id": str(row["id"]),
        "capture_id": str(capture_id),
        "frame_id": str(row["frame_id"]),
        "camera_id": row["camera_id"],
        "label": row["label"],
        "box_xyxy": row["box_xyxy"],
        "width": row["width"],
        "height": row["height"],
        "mask_key": row["mask_key"],
        "embedding_key": row["embedding_key"],
        "embedding_metadata": row["embedding_metadata"],
        "debug_crop_key": row["debug_crop_key"],
    }


def features(value, store):
    result = dict(value)
    if value.get("mask_key"):
        blob = store.stat(value["mask_key"])
        result["mask"] = decode_mask(Mask.model_validate_json(store.get(blob)))
    metadata = value.get("embedding_metadata") or {}
    if value.get("embedding_key"):
        blob = store.stat(value["embedding_key"])
        if blob.sha256 != metadata["sha256"]:
            raise ValueError("embedding checksum mismatch")
        vector = np.frombuffer(store.get(blob), dtype="<f4")
        if (
            len(vector) != metadata["dimension"]
            or not np.isfinite(vector).all()
            or abs(np.linalg.norm(vector) - 1) > 1e-5
        ):
            raise ValueError("invalid stored embedding")
        result.update(feature=vector, embedding_model=metadata["model"])
    return result


def reference(conn, run, capture, camera, explicit):
    query = (
        select(processing_runs.c.id)
        .join(captures, captures.c.id == processing_runs.c.capture_id)
        .outerjoin(revisions, revisions.c.capture_id == captures.c.id)
        .where(
            captures.c.environment_id == capture["environment_id"],
            captures.c.id != capture["id"],
            captures.c.captured_at <= capture["captured_at"],
            processing_runs.c.status == "succeeded",
            select(artifacts.c.id)
            .where(artifacts.c.source_id == processing_runs.c.id, artifacts.c.kind == "tracking")
            .exists(),
        )
    )
    if explicit:
        query = query.where(captures.c.id == UUID(explicit))
    return conn.execute(
        query.order_by(
            case((revisions.c.id.is_not(None), 0), else_=1),
            revisions.c.created_at.desc().nullslast(),
            captures.c.captured_at.desc(),
            processing_runs.c.completed_at.desc(),
            processing_runs.c.id,
        ).limit(1)
    ).scalar()


def associate(repository, run, capture, store):
    settings = TrackingSettings.model_validate(run["model_manifest"]["config"].get("tracking", {}))
    explicit = run["model_manifest"]["config"].get("reference_capture_id")
    reports, states = {}, []
    with repository.engine.begin() as conn:
        conn.execute(
            select(environments)
            .where(environments.c.id == capture["environment_id"])
            .with_for_update()
        )
        if conn.execute(
            select(view_track_snapshots.c.id).where(view_track_snapshots.c.run_id == run["id"])
        ).first():
            raise AppError("already_tracked", "Run tracking snapshots already exist", 409)
        for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
            ref = reference(conn, run, capture, camera, explicit)
            accepted = (
                None
                if explicit
                else conn.execute(
                    select(revisions)
                    .join(captures, captures.c.id == revisions.c.capture_id)
                    .where(
                        revisions.c.environment_id == capture["environment_id"],
                        captures.c.id != capture["id"],
                        captures.c.captured_at <= capture["captured_at"],
                    )
                    .order_by(revisions.c.created_at.desc(), revisions.c.id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            previous = (
                []
                if ref is None
                else [
                    dict(r.state)
                    for r in conn.execute(
                        select(view_track_snapshots).where(
                            view_track_snapshots.c.run_id == ref,
                            view_track_snapshots.c.camera_id == camera,
                        )
                    ).mappings()
                ]
            )
            if accepted:
                previous = [
                    dict(r.state)
                    for r in conn.execute(
                        select(revision_track_snapshots).where(
                            revision_track_snapshots.c.revision_id == accepted["id"],
                            revision_track_snapshots.c.camera_id == camera,
                        )
                    ).mappings()
                ]
            if explicit and ref is None:
                raise AppError(
                    "invalid_reference",
                    "Reference has no eligible same-camera processed state",
                    422,
                )
            current = [
                observation(dict(row), capture["id"])
                for row in conn.execute(
                    select(detections, frames.c.camera_id, frames.c.width, frames.c.height)
                    .join(frames, detections.c.frame_id == frames.c.id)
                    .where(detections.c.run_id == run["id"], frames.c.camera_id == camera)
                ).mappings()
            ]
            old_inputs = [
                features(s["observation"], store) | {"view_track_id": s["view_track_id"]}
                for s in previous
            ]
            new_inputs = [features(o, store) for o in current]
            report = match(camera, old_inputs, new_inputs, settings)
            report.update(
                camera_id=camera,
                reference_run_id=str(ref) if ref else None,
                reference_capture_id=str(accepted["capture_id"])
                if accepted
                else (
                    str(
                        conn.scalar(
                            select(processing_runs.c.capture_id).where(processing_runs.c.id == ref)
                        )
                    )
                    if ref
                    else None
                ),
                reference_revision_id=str(accepted["id"]) if accepted else None,
                run_id=str(run["id"]),
            )
            reports[camera] = report
            chosen = {c["detection_id"]: c for c in report["matches"]}
            used = {c["track_id"] for c in report["matches"]}
            old_map = {s["view_track_id"]: s for s in previous}
            for obs in current:
                candidate = chosen.get(obs["id"])
                track_id = (
                    UUID(candidate["track_id"])
                    if candidate
                    else uuid5(run["id"], f"{camera}:{obs['id']}")
                )
                uncertain = obs["id"] in report["uncertain_detections"]
                before = old_map.get(str(track_id))
                state = {
                    "view_track_id": str(track_id),
                    "camera_id": camera,
                    "capture_id": str(capture["id"]),
                    "status": "observed",
                    "missing_count": 0,
                    "observation": obs,
                    "before": before["observation"] if before else None,
                    "before_missing_count": before["missing_count"] if before else 0,
                    "uncertain": uncertain,
                    "match": candidate,
                    "reference_run_id": str(ref) if ref else None,
                    "reference_revision_id": str(accepted["id"]) if accepted else None,
                }
                if not candidate:
                    conn.execute(
                        insert(view_tracks).values(
                            id=track_id,
                            environment_id=capture["environment_id"],
                            camera_id=camera,
                            status="observed",
                            first_seen_at=capture["captured_at"],
                            last_seen_capture_id=capture["id"],
                            missing_count=0,
                        )
                    )
                conn.execute(
                    insert(track_observations).values(
                        environment_id=capture["environment_id"],
                        run_id=run["id"],
                        view_track_id=track_id,
                        detection_id=UUID(obs["id"]),
                        capture_id=capture["id"],
                        match_score=candidate["score"] if candidate else 0,
                        match_metadata={
                            "decision": "uncertain"
                            if uncertain
                            else "matched"
                            if candidate
                            else "birth",
                            "candidate": candidate,
                        },
                    )
                )
                states.append(state)
            for before in previous:
                if before["view_track_id"] not in used:
                    states.append(
                        before
                        | {
                            "capture_id": str(capture["id"]),
                            "status": "unobserved",
                            "missing_count": before["missing_count"] + 1,
                            "before": before["observation"],
                            "uncertain": before["view_track_id"] in report["uncertain_tracks"],
                            "match": None,
                            "reference_run_id": str(ref),
                            "reference_revision_id": str(accepted["id"]) if accepted else None,
                        }
                    )
        for state in states:
            conn.execute(
                insert(view_track_snapshots).values(
                    environment_id=capture["environment_id"],
                    run_id=run["id"],
                    view_track_id=UUID(state["view_track_id"]),
                    camera_id=state["camera_id"],
                    capture_id=capture["id"],
                    state=state,
                )
            )
            # Registry is advisory latest state; immutable per-run snapshots are authoritative.
            conn.execute(
                update(view_tracks)
                .where(view_tracks.c.id == UUID(state["view_track_id"]))
                .values(
                    status=state["status"],
                    missing_count=state["missing_count"],
                    **(
                        {"last_seen_capture_id": capture["id"]}
                        if state["status"] == "observed"
                        else {}
                    ),
                )
            )
    return {"schema_version": 1, "run_id": str(run["id"]), "cameras": reports, "states": states}

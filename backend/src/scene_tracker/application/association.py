"""Run-scoped camera-local tracks; all physical-object links remain untouched."""

from uuid import UUID, uuid5

import numpy as np
from sqlalchemy import insert, select, update

from scene_tracker.application.references import select_reference
from scene_tracker.core.errors import AppError
from scene_tracker.core.tracking_settings import TrackingSettings
from scene_tracker.domain.contracts import Mask
from scene_tracker.infrastructure.db.models import (
    detections,
    environments,
    frames,
    revision_track_snapshots,
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


def appearance_prototype(observation):
    """An immutable reference to one stored observation, never an invented/averaged vector."""
    if not observation.get("embedding_key"):
        return None
    return {
        "strategy": "last_confident_embedding_v1",
        "detection_id": observation["id"],
        "capture_id": observation["capture_id"],
        "frame_id": observation["frame_id"],
        "camera_id": observation["camera_id"],
        "embedding_key": observation["embedding_key"],
        "embedding_metadata": observation["embedding_metadata"],
    }


def previous_prototype(state):
    # Legacy snapshots remain immutable; derive a prototype in memory if they predate this field.
    return state.get("appearance_prototype") or appearance_prototype(state["observation"])


def track_features(state, store):
    value = dict(state["observation"])
    prototype = previous_prototype(state)
    if prototype:
        if prototype["camera_id"] != state["camera_id"]:
            raise ValueError("cross-camera appearance prototype is forbidden")
        value.update(
            embedding_key=prototype["embedding_key"],
            embedding_metadata=prototype["embedding_metadata"],
        )
    return features(value, store) | {
        "view_track_id": state["view_track_id"],
        "appearance_reference": prototype,
    }


def updated_prototype(before, observation, candidate, settings):
    prototype = appearance_prototype(observation)
    if before is None:
        return prototype
    if (
        prototype
        and candidate
        and not candidate["embedding_missing"]
        and candidate["terms"]["appearance"] >= settings.minimum_appearance
    ):
        return prototype
    return previous_prototype(before)


def associate(repository, run, capture, store):
    settings = TrackingSettings.model_validate(run["model_manifest"]["config"].get("tracking", {}))
    config = run["model_manifest"]["config"]
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
        baseline = config.get("reference") or select_reference(
            conn, capture, config.get("reference_capture_id")
        )
        reference_run = baseline["run_id"]
        reference_revision = baseline["revision_id"]
        previous_states = []
        if reference_revision or reference_run:
            table, source_id = (
                (revision_track_snapshots, revision_track_snapshots.c.revision_id)
                if reference_revision
                else (view_track_snapshots, view_track_snapshots.c.run_id)
            )
            previous_states = conn.scalars(
                select(table.c.state).where(source_id == UUID(reference_revision or reference_run))
            ).all()
        for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
            previous = [state for state in previous_states if state["camera_id"] == camera]
            current = [
                observation(dict(row), capture["id"])
                for row in conn.execute(
                    select(detections, frames.c.camera_id, frames.c.width, frames.c.height)
                    .join(frames, detections.c.frame_id == frames.c.id)
                    .where(detections.c.run_id == run["id"], frames.c.camera_id == camera)
                ).mappings()
            ]
            old_inputs = [track_features(s, store) for s in previous]
            new_inputs = [features(o, store) for o in current]
            report = match(camera, old_inputs, new_inputs, settings)
            report.update(
                camera_id=camera,
                reference_run_id=reference_run,
                reference_kind=baseline["kind"],
                reference_capture_id=baseline["capture_id"],
                reference_revision_id=reference_revision,
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
                uncertain = obs["id"] in report["uncertain_detections"] or bool(
                    candidate and candidate["embedding_missing"]
                )
                before = old_map.get(str(track_id))
                state = {
                    "schema_version": 2,
                    "run_id": str(run["id"]),
                    "view_track_id": str(track_id),
                    "appearance_prototype": updated_prototype(before, obs, candidate, settings),
                    "camera_id": camera,
                    "capture_id": str(capture["id"]),
                    "status": "observed",
                    "missing_count": 0,
                    "observation": obs,
                    "before": before["observation"] if before else None,
                    "before_missing_count": before["missing_count"] if before else 0,
                    "uncertain": uncertain,
                    "match": candidate,
                    "reference_run_id": reference_run,
                    "reference_revision_id": reference_revision,
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
                            "schema_version": 2,
                            "run_id": str(run["id"]),
                            "appearance_prototype": previous_prototype(before),
                            "capture_id": str(capture["id"]),
                            "status": "unobserved",
                            "missing_count": before["missing_count"] + 1,
                            "before": before["observation"],
                            "uncertain": before["view_track_id"] in report["uncertain_tracks"],
                            "match": None,
                            "reference_run_id": reference_run,
                            "reference_revision_id": reference_revision,
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
    return {
        "schema_version": 2,
        "run_id": str(run["id"]),
        "reference": baseline,
        "cameras": reports,
        "states": states,
    }

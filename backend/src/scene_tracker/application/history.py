"""Immutable revision provenance, approved evidence and endpoint comparisons."""

import json

from sqlalchemy import select

from scene_tracker.application.evidence import EvidenceReader
from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import (
    artifacts,
    change_proposals,
    frames,
    processing_runs,
    revision_changes,
    revision_track_snapshots,
    revisions,
    view_tracks,
)


def revision_row(conn, revision_id):
    row = conn.execute(select(revisions).where(revisions.c.id == revision_id)).mappings().first()
    if row is None:
        raise AppError("not_found", "Revision not found", 404)
    return dict(row)


def provenance(conn, capture_id, run_ids, origin="commit_snapshot"):
    run_ids = sorted(set(run_ids), key=str)
    runs = list(
        conn.execute(
            select(processing_runs)
            .where(processing_runs.c.id.in_(run_ids))
            .order_by(processing_runs.c.id)
        ).mappings()
    )
    source_frames = list(
        conn.execute(
            select(frames).where(frames.c.capture_id == capture_id).order_by(frames.c.camera_id)
        ).mappings()
    )
    source_artifacts = list(
        conn.execute(
            select(artifacts)
            .where(artifacts.c.source_id.in_(run_ids))
            .order_by(artifacts.c.source_id, artifacts.c.storage_key)
        ).mappings()
    )
    return json.loads(
        json.dumps(
            {
                "schema_version": "1.0",
                "origin": origin,
                "capture_id": capture_id,
                "run_ids": run_ids,
                "runs": [dict(r) for r in runs],
                "frames": [dict(f) for f in source_frames],
                "artifacts": [dict(a) for a in source_artifacts],
            },
            default=str,
        )
    )


def states(conn, revision_id):
    if revision_id is None:
        return {}
    rows = conn.execute(
        select(revision_track_snapshots)
        .where(
            revision_track_snapshots.c.revision_id == revision_id,
        )
        .order_by(revision_track_snapshots.c.camera_id, revision_track_snapshots.c.view_track_id)
    )
    return {str(row.view_track_id): row.state for row in rows}


def revision_evidence(services, revision_id):
    with services.repository.engine.connect() as conn:
        revision = revision_row(conn, revision_id)
        approved = states(conn, revision_id)
        events = list(
            conn.scalars(
                select(revision_changes.c.applied_payload)
                .where(revision_changes.c.revision_id == revision_id)
                .order_by(revision_changes.c.proposal_id)
            )
        )
        source = revision.get("provenance")
        if source is None:
            run_ids = conn.scalars(
                select(change_proposals.c.run_id)
                .join(revision_changes, revision_changes.c.proposal_id == change_proposals.c.id)
                .where(revision_changes.c.revision_id == revision_id)
            ).all()
            source = provenance(conn, revision["capture_id"], run_ids, origin="derived_legacy")
    reader = EvidenceReader(services, revision["environment_id"])
    capture = services.repository.capture(revision["capture_id"])
    source_captures = {str(capture["id"])}
    for event in events:
        for side in ("before_ref", "after_ref"):
            if (ref := event.get(side)) and "capture_id" in ref:
                source_captures.add(ref["capture_id"])
    return {
        "revision": revision,
        "provenance": source,
        "source_images": [reader.frame(frame) for frame in capture["frames"]],
        "approved_tracks": [reader.track(state) for state in approved.values()],
        "changes": [reader.change(event) for event in events],
        "highlight_paths": [
            f"/api/v1/captures/{capture_id}/highlights?camera_id={camera}&revision_id={revision_id}"
            for capture_id in sorted(source_captures)
            for camera in ("cam_01", "cam_02", "cam_03", "cam_04")
        ],
    }


def ancestor_ids(conn, revision):
    ids = set()
    while revision:
        ids.add(revision["id"])
        revision = revision_row(conn, revision["parent_id"]) if revision["parent_id"] else None
    return ids


def semantic_state(state, mask_digest):
    """Endpoint content ignores run IDs, capture times and accumulated missing counters."""
    ref = state["observation"]
    width, height = ref["width"], ref["height"]
    return {
        "status": state["status"],
        "label": ref["label"],
        "box_xyxy": [
            round(value / (width if index % 2 == 0 else height), 6)
            for index, value in enumerate(ref["box_xyxy"])
        ],
        "appearance": (ref.get("embedding_metadata") or {}).get("sha256"),
        "mask": mask_digest(ref["mask_key"]) if ref.get("mask_key") else None,
        "uncertain": state.get("uncertain", False),
    }


def compare_states(before, after, mask_digest=lambda key: key):
    result = []
    for track_id in sorted(before.keys() | after.keys()):
        old, new = before.get(track_id), after.get(track_id)
        if old is None:
            kind, fields = "added", ["presence"]
        elif new is None:
            kind, fields = "removed", ["presence"]
        else:
            old_value = semantic_state(old, mask_digest)
            new_value = semantic_state(new, mask_digest)
            fields = [key for key in old_value if old_value[key] != new_value[key]]
            kind = "changed" if fields else "unchanged"
            if old["status"] != new["status"]:
                kind = "missing" if new["status"] == "unobserved" else "restored"
        result.append(
            {
                "view_track_id": track_id,
                "camera_id": (new or old)["camera_id"],
                "kind": kind,
                "fields": fields,
                "before": old,
                "after": new,
            }
        )
    return sorted(result, key=lambda item: (item["camera_id"], item["view_track_id"]))


def state_comparison(services, before_id, after_id):
    with services.repository.engine.connect() as conn:
        before = revision_row(conn, before_id)
        after = revision_row(conn, after_id)
        if before["environment_id"] != after["environment_id"]:
            raise AppError("invalid_reference", "Compare revisions in the same environment", 422)
        if before_id == after_id:
            direction = "identical"
        elif before_id in ancestor_ids(conn, after):
            direction = "forward"
        elif after_id in ancestor_ids(conn, before):
            direction = "reverse"
        else:
            raise AppError("invalid_reference", "Revisions must share a linear history", 422)
        before_states, after_states = states(conn, before_id), states(conn, after_id)
    reader = EvidenceReader(services, before["environment_id"])

    def mask_digest(key):
        asset = reader.asset(key)
        return asset["sha256"] or key

    items = compare_states(before_states, after_states, mask_digest)
    for item in items:
        for side in ("before", "after"):
            if item[side]:
                item[side] = reader.track(item[side])
    return {
        "from_revision_id": before_id,
        "revision_id": after_id,
        "direction": direction,
        "items": items,
    }


def accepted_track_history(services, track_id, limit, offset):
    with services.repository.engine.connect() as conn:
        registry = (
            conn.execute(select(view_tracks).where(view_tracks.c.id == track_id)).mappings().first()
        )
        if registry is None:
            raise AppError("not_found", "View track not found", 404)
        rows = list(
            conn.execute(
                select(revisions, revision_track_snapshots.c.state)
                .join(
                    revision_track_snapshots,
                    revision_track_snapshots.c.revision_id == revisions.c.id,
                )
                .where(
                    revision_track_snapshots.c.view_track_id == track_id,
                    select(revision_changes.c.id)
                    .where(
                        revision_changes.c.revision_id == revisions.c.id,
                        revision_changes.c.applied_payload["view_track_id"].astext == str(track_id),
                    )
                    .exists(),
                )
                .order_by(revisions.c.created_at, revisions.c.id)
                .limit(limit)
                .offset(offset)
            ).mappings()
        )
        reader = EvidenceReader(services, registry["environment_id"])
        items = []
        for row in rows:
            prior = states(conn, row["parent_id"]).get(str(track_id))
            events = conn.scalars(
                select(revision_changes.c.applied_payload)
                .where(
                    revision_changes.c.revision_id == row["id"],
                    revision_changes.c.applied_payload["view_track_id"].astext == str(track_id),
                )
                .order_by(revision_changes.c.proposal_id)
            )
            items.append(
                {
                    "revision": dict(row),
                    "state": reader.track(row["state"]),
                    "before": reader.track(prior) if prior else None,
                    "changes": [reader.change(event) for event in events],
                }
            )
    return {
        "view_track_id": track_id,
        "camera_id": registry["camera_id"],
        "environment_id": registry["environment_id"],
        "items": items,
        "limit": limit,
        "offset": offset,
    }

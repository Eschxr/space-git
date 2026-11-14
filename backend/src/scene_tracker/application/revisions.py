"""Atomic review/commit operations. Approved state changes only through selected events."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update

from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import (
    change_proposals as proposals,
)
from scene_tracker.infrastructure.db.models import (
    environments,
    processing_runs,
    revision_changes,
    revision_track_snapshots,
    revisions,
    view_track_snapshots,
)


def require(row, message="Resource not found"):
    if row is None:
        raise AppError("not_found", message, 404)
    return dict(row)


def latest(conn, environment_id):
    return (
        conn.execute(
            select(revisions)
            .where(revisions.c.environment_id == environment_id)
            .order_by(revisions.c.created_at.desc(), revisions.c.id)
            .limit(1)
        )
        .mappings()
        .first()
    )


def decide(repository, proposal_id, status, reason):
    with repository.engine.begin() as conn:
        row = require(
            conn.execute(select(proposals).where(proposals.c.id == proposal_id).with_for_update())
            .mappings()
            .first()
        )
        if conn.execute(
            select(revision_changes.c.id).where(revision_changes.c.proposal_id == proposal_id)
        ).first():
            if row["status"] == status:
                return row
            raise AppError("already_committed", "Committed proposals are immutable", 409)
        run = require(
            conn.execute(select(processing_runs).where(processing_runs.c.id == row["run_id"]))
            .mappings()
            .first()
        )
        if run["status"] != "succeeded":
            raise AppError("run_not_ready", "Only succeeded runs can be reviewed", 409)
        conn.execute(
            update(proposals)
            .where(proposals.c.id == proposal_id)
            .values(status=status, reason=reason)
        )
        return row | {"status": status, "reason": reason}


def commit(repository, environment_id, body):
    capture_id = body.capture_id
    ids = sorted(set(body.proposal_ids), key=str)
    digest = hashlib.sha256(
        json.dumps(
            {"capture_id": str(capture_id), "ids": list(map(str, ids)), "message": body.message},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    with repository.engine.begin() as conn:
        require(
            conn.execute(
                select(environments).where(environments.c.id == environment_id).with_for_update()
            )
            .mappings()
            .first()
        )
        prior = (
            conn.execute(
                select(revisions).where(
                    revisions.c.environment_id == environment_id,
                    revisions.c.idempotency_key == body.idempotency_key,
                )
            )
            .mappings()
            .first()
        )
        if prior:
            if prior["request_hash"] != digest:
                raise AppError(
                    "idempotency_conflict", "Key already used with different content", 409
                )
            return dict(prior)
        parent = latest(conn, environment_id)
        selected = list(
            conn.execute(
                select(proposals)
                .where(proposals.c.id.in_(ids))
                .order_by(proposals.c.id)
                .with_for_update()
            ).mappings()
        )
        if len(selected) != len(ids) or not selected:
            raise AppError("invalid_changes", "Select existing accepted proposals", 422)
        run_ids = {p["run_id"] for p in selected}
        if len(run_ids) != 1 or any(
            p["environment_id"] != environment_id
            or p["status"] != "accepted"
            or not p["view_track_id"]
            for p in selected
        ):
            raise AppError(
                "invalid_changes", "Changes must be accepted, camera-local and from one run", 422
            )
        run = require(
            conn.execute(select(processing_runs).where(processing_runs.c.id == next(iter(run_ids))))
            .mappings()
            .first()
        )
        if run["capture_id"] != capture_id or run["status"] != "succeeded":
            raise AppError(
                "invalid_changes", "Run must succeed and belong to the revision capture", 422
            )
        if conn.execute(
            select(revision_changes.c.id).where(revision_changes.c.proposal_id.in_(ids))
        ).first():
            raise AppError("already_committed", "A selected proposal is already committed", 409)
        parent_id = str(parent["id"]) if parent else None
        if any(p["evidence"].get("reference_revision_id") != parent_id for p in selected):
            raise AppError("stale_baseline", "Reprocess against the latest accepted revision", 409)
        state = (
            {}
            if parent is None
            else {
                str(r.view_track_id): dict(r.state)
                for r in conn.execute(
                    select(revision_track_snapshots).where(
                        revision_track_snapshots.c.revision_id == parent["id"]
                    )
                ).mappings()
            }
        )
        snapshots = {
            str(r.view_track_id): dict(r.state)
            for r in conn.execute(
                select(view_track_snapshots).where(view_track_snapshots.c.run_id == run["id"])
            ).mappings()
        }
        revision_id = uuid4()
        values = {
            "id": revision_id,
            "environment_id": environment_id,
            "parent_id": parent["id"] if parent else None,
            "capture_id": capture_id,
            "created_at": datetime.now(UTC),
            "message": body.message,
            "idempotency_key": body.idempotency_key,
            "request_hash": digest,
        }
        conn.execute(insert(revisions).values(**values))
        for proposal in selected:
            track = str(proposal["view_track_id"])
            if track not in snapshots:
                raise AppError("invalid_changes", "Missing track state", 422)
            state[track] = snapshots[track]
            # Copy all evidence: later review cannot change a committed event.
            payload = {k: str(v) if isinstance(v, UUID) else v for k, v in proposal.items()}
            conn.execute(
                insert(revision_changes).values(
                    environment_id=environment_id,
                    revision_id=revision_id,
                    proposal_id=proposal["id"],
                    applied_payload=payload,
                )
            )
        for track, value in state.items():
            conn.execute(
                insert(revision_track_snapshots).values(
                    environment_id=environment_id,
                    revision_id=revision_id,
                    view_track_id=UUID(track),
                    camera_id=value["camera_id"],
                    state=value,
                )
            )
        return values

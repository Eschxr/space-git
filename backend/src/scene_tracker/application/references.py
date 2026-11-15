"""Select one immutable camera-local baseline for all four views."""

from uuid import UUID

from sqlalchemy import select

from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import artifacts, captures, processing_runs, revisions


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


def select_reference(conn, capture, explicit=None):
    environment_id = capture["environment_id"]
    head = latest(conn, environment_id)
    eligible_captures = (
        captures.c.environment_id == environment_id,
        captures.c.captured_at <= capture["captured_at"],
    )
    inspection_reason = None
    approved = None
    if explicit:
        inspection_reason = "explicit_reference"
    elif head:
        approved = (
            conn.execute(
                select(revisions)
                .join(captures, revisions.c.capture_id == captures.c.id)
                .where(revisions.c.environment_id == environment_id, *eligible_captures)
                .order_by(revisions.c.created_at.desc(), revisions.c.id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if approved is None or approved["id"] != head["id"]:
            inspection_reason = "backdated_capture"
        elif approved["capture_id"] == capture["id"]:
            inspection_reason = "approved_capture_rerun"

    if approved is not None:
        return {
            "kind": "accepted_revision",
            "revision_id": str(approved["id"]),
            "capture_id": str(approved["capture_id"]),
            "run_id": None,
            "inspection_reason": inspection_reason,
        }

    query = (
        select(processing_runs.c.id, processing_runs.c.capture_id)
        .join(captures, captures.c.id == processing_runs.c.capture_id)
        .where(
            *eligible_captures,
            captures.c.id != capture["id"],
            processing_runs.c.status == "succeeded",
            select(artifacts.c.id)
            .where(artifacts.c.source_id == processing_runs.c.id, artifacts.c.kind == "tracking")
            .exists(),
        )
    )
    if explicit:
        query = query.where(captures.c.id == UUID(str(explicit)))
    run = conn.execute(
        query.order_by(
            captures.c.captured_at.desc(),
            processing_runs.c.completed_at.desc().nullslast(),
            processing_runs.c.id,
        ).limit(1)
    ).first()
    if explicit and run is None:
        raise AppError(
            "invalid_reference", "Reference requires an eligible succeeded tracking run", 422
        )
    return {
        "kind": "processed_run" if run else "initial",
        "revision_id": None,
        "capture_id": str(run.capture_id) if run else None,
        "run_id": str(run.id) if run else None,
        "inspection_reason": inspection_reason,
    }

"""Read-only camera-local registry and immutable run history; no physical identity links."""

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from scene_tracker.api.routes.captures import ServicesDep
from scene_tracker.api.schemas.history import AcceptedTrackPage
from scene_tracker.application.history import accepted_track_history
from scene_tracker.application.revisions import require
from scene_tracker.infrastructure.db.models import (
    captures,
    processing_runs,
    view_track_snapshots,
    view_tracks,
)

router = APIRouter(prefix="/api/v1")


@router.get("/view-tracks/{track_id}/revisions", response_model=AcceptedTrackPage)
def accepted_history(
    track_id: UUID,
    services: ServicesDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return accepted_track_history(services, track_id, limit, offset)


def track(conn, track_id):
    return require(
        conn.execute(select(view_tracks).where(view_tracks.c.id == track_id)).mappings().first(),
        "View track not found",
    )


@router.get("/view-tracks/{track_id}")
def get_track(track_id: UUID, services: ServicesDep):
    with services.repository.engine.connect() as conn:
        return track(conn, track_id)


@router.get("/view-tracks/{track_id}/history")
def history(
    track_id: UUID,
    services: ServicesDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with services.repository.engine.connect() as conn:
        registry = track(conn, track_id)
        rows = conn.execute(
            select(
                view_track_snapshots,
                processing_runs.c.status.label("run_status"),
                captures.c.captured_at,
            )
            .join(processing_runs, processing_runs.c.id == view_track_snapshots.c.run_id)
            .join(captures, captures.c.id == view_track_snapshots.c.capture_id)
            .where(view_track_snapshots.c.view_track_id == track_id)
            .order_by(
                captures.c.captured_at, processing_runs.c.started_at, view_track_snapshots.c.run_id
            )
            .limit(limit)
            .offset(offset)
        ).mappings()
        return {
            "view_track_id": track_id,
            "camera_id": registry["camera_id"],
            "environment_id": registry["environment_id"],
            "items": [dict(row) for row in rows],
            "limit": limit,
            "offset": offset,
        }

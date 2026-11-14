from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from scene_tracker.api.routes.captures import ServicesDep
from scene_tracker.application.revisions import commit, decide, require
from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import (
    change_proposals,
    revision_changes,
    revision_track_snapshots,
    revisions,
)

router = APIRouter(prefix="/api/v1")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted", "rejected", "needs_review"]
    reason: str | None = Field(None, max_length=2000)


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture_id: UUID
    proposal_ids: list[UUID] = Field(min_length=1, max_length=1000)
    message: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=200)


def visualize(item, services, environment_id):
    store = services.store_factory(environment_id)
    value = dict(item)
    for side in ("before_ref", "after_ref"):
        ref = value.get(side)
        if ref:
            frame = next(
                f
                for f in services.repository.capture(UUID(ref["capture_id"]))["frames"]
                if str(f["id"]) == ref["frame_id"]
            )
            value[side] = dict(ref) | {"image_url": store.presign(store.stat(frame["storage_key"]))}
            for field in ("mask_key", "debug_crop_key"):
                if ref.get(field):
                    value[side][field.replace("_key", "_url")] = store.presign(
                        store.stat(ref[field])
                    )
    return value


@router.get("/processing-runs/{run_id}/changes")
def list_changes(
    run_id: UUID,
    services: ServicesDep,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    run = services.repository.run(run_id)
    with services.repository.engine.connect() as conn:
        rows = conn.execute(
            select(change_proposals)
            .where(change_proposals.c.run_id == run_id)
            .order_by(change_proposals.c.camera_id, change_proposals.c.id)
            .limit(limit)
            .offset(offset)
        ).mappings()
        items = [visualize(r, services, run["environment_id"]) for r in rows]
    return {"run_id": run_id, "items": items, "limit": limit, "offset": offset}


@router.post("/change-proposals/{proposal_id}/decision")
def review(proposal_id: UUID, body: Decision, services: ServicesDep):
    return decide(services.repository, proposal_id, body.status, body.reason)


@router.post("/environments/{environment_id}/revisions", status_code=201)
def create_revision(environment_id: UUID, body: RevisionCreate, services: ServicesDep):
    return commit(services.repository, environment_id, body)


@router.get("/environments/{environment_id}/revisions")
def list_revisions(
    environment_id: UUID,
    services: ServicesDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    services.repository.environment(environment_id)
    with services.repository.engine.connect() as conn:
        return {
            "items": [
                dict(r)
                for r in conn.execute(
                    select(revisions)
                    .where(revisions.c.environment_id == environment_id)
                    .order_by(revisions.c.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                ).mappings()
            ],
            "limit": limit,
            "offset": offset,
        }


@router.get("/revisions/{revision_id}")
def get_revision(revision_id: UUID, services: ServicesDep):
    with services.repository.engine.connect() as conn:
        revision = require(
            conn.execute(select(revisions).where(revisions.c.id == revision_id)).mappings().first()
        )
        return revision | {
            "tracks": [
                dict(r.state)
                for r in conn.execute(
                    select(revision_track_snapshots)
                    .where(revision_track_snapshots.c.revision_id == revision_id)
                    .order_by(
                        revision_track_snapshots.c.camera_id,
                        revision_track_snapshots.c.view_track_id,
                    )
                ).mappings()
            ]
        }


@router.get("/revisions/{revision_id}/diff")
def diff(revision_id: UUID, services: ServicesDep, from_revision_id: UUID | None = None):
    with services.repository.engine.connect() as conn:
        revision = require(
            conn.execute(select(revisions).where(revisions.c.id == revision_id)).mappings().first()
        )
        target = from_revision_id if from_revision_id else revision["parent_id"]
        chain, cursor = [], revision
        while cursor and cursor["id"] != target:
            chain.append(cursor["id"])
            cursor = (
                None
                if cursor["parent_id"] is None
                else require(
                    conn.execute(select(revisions).where(revisions.c.id == cursor["parent_id"]))
                    .mappings()
                    .first()
                )
            )
        if target is not None and cursor is None:
            raise AppError("invalid_reference", "Diff reference must be an ancestor revision", 422)
        changes = []
        for rid in reversed(chain):
            for row in conn.execute(
                select(revision_changes)
                .where(revision_changes.c.revision_id == rid)
                .order_by(revision_changes.c.proposal_id)
            ).mappings():
                changes.append(
                    visualize(row["applied_payload"], services, revision["environment_id"])
                )
        return {"revision_id": revision_id, "from_revision_id": target, "changes": changes}

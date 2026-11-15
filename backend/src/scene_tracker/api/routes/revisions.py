from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from scene_tracker.api.routes.captures import ServicesDep
from scene_tracker.api.schemas.history import (
    DecisionPage,
    RevisionEvidence,
    RevisionMetadata,
    RevisionPage,
    RevisionResponse,
    StateComparison,
)
from scene_tracker.application.evidence import EvidenceReader
from scene_tracker.application.history import revision_evidence, state_comparison
from scene_tracker.application.revisions import commit, decide, require
from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import (
    change_proposals,
    review_decisions,
    revision_changes,
    revision_track_snapshots,
    revisions,
)

router = APIRouter(prefix="/api/v1")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["accepted", "rejected", "needs_review"]
    reason: str | None = Field(None, max_length=2000)
    reviewer: str = Field(default="local-operator", min_length=1, max_length=200)
    idempotency_key: str | None = Field(None, min_length=1, max_length=200)


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture_id: UUID
    proposal_ids: list[UUID] = Field(min_length=1, max_length=1000)
    message: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=200)


def visualize(item, services, environment_id):
    return EvidenceReader(services, environment_id).change(item)


@router.get("/processing-runs/{run_id}/changes")
def list_changes(
    run_id: UUID,
    services: ServicesDep,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    run = services.repository.run(run_id)
    reader = EvidenceReader(services, run["environment_id"])
    with services.repository.engine.connect() as conn:
        rows = conn.execute(
            select(change_proposals)
            .where(change_proposals.c.run_id == run_id)
            .order_by(change_proposals.c.camera_id, change_proposals.c.id)
            .limit(limit)
            .offset(offset)
        ).mappings()
        items = [reader.change(r) for r in rows]
    return {"run_id": run_id, "items": items, "limit": limit, "offset": offset}


@router.post("/change-proposals/{proposal_id}/decision")
def review(proposal_id: UUID, body: Decision, services: ServicesDep):
    return decide(
        services.repository,
        proposal_id,
        body.status,
        body.reason,
        body.reviewer,
        body.idempotency_key,
    )


@router.get("/change-proposals/{proposal_id}/decisions", response_model=DecisionPage)
def decision_history(
    proposal_id: UUID,
    services: ServicesDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with services.repository.engine.connect() as conn:
        proposal = require(
            conn.execute(select(change_proposals).where(change_proposals.c.id == proposal_id))
            .mappings()
            .first()
        )
        rows = conn.execute(
            select(review_decisions)
            .where(
                review_decisions.c.proposal_id == proposal_id,
            )
            .order_by(review_decisions.c.decided_at, review_decisions.c.id)
            .limit(limit)
            .offset(offset)
        ).mappings()
        return {
            "proposal_id": proposal_id,
            "current_status": proposal["status"],
            "current_reason": proposal["reason"],
            "items": list(rows),
            "limit": limit,
            "offset": offset,
        }


@router.post(
    "/environments/{environment_id}/revisions", status_code=201, response_model=RevisionMetadata
)
def create_revision(environment_id: UUID, body: RevisionCreate, services: ServicesDep):
    return commit(services.repository, environment_id, body)


@router.get("/environments/{environment_id}/revisions", response_model=RevisionPage)
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


@router.get("/revisions/{revision_id}", response_model=RevisionResponse)
def get_revision(revision_id: UUID, services: ServicesDep):
    with services.repository.engine.connect() as conn:
        revision = require(
            conn.execute(select(revisions).where(revisions.c.id == revision_id)).mappings().first()
        )
        return revision | {
            "evidence_path": f"/api/v1/revisions/{revision_id}/evidence",
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
            ],
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
        reader = EvidenceReader(services, revision["environment_id"])
        for rid in reversed(chain):
            for row in conn.execute(
                select(revision_changes)
                .where(revision_changes.c.revision_id == rid)
                .order_by(revision_changes.c.proposal_id)
            ).mappings():
                changes.append(reader.change(row["applied_payload"]))
        return {"revision_id": revision_id, "from_revision_id": target, "changes": changes}


@router.get("/revisions/{revision_id}/evidence", response_model=RevisionEvidence)
def evidence(revision_id: UUID, services: ServicesDep):
    return revision_evidence(services, revision_id)


@router.get("/revisions/{revision_id}/compare", response_model=StateComparison)
def compare(revision_id: UUID, from_revision_id: UUID, services: ServicesDep):
    return state_comparison(services, from_revision_id, revision_id)

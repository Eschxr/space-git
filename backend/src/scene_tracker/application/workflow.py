"""Discover capture attempts, review progress and the approved head."""

from collections import Counter

from sqlalchemy import select

from scene_tracker.application.evidence import EvidenceReader
from scene_tracker.application.references import latest
from scene_tracker.infrastructure.db.models import (
    change_proposals,
    revision_changes,
    view_track_snapshots,
)


def run_summary(conn, run):
    manifest = run["model_manifest"]
    proposals = list(
        conn.execute(
            select(change_proposals).where(
                change_proposals.c.run_id == run["id"],
            )
        ).mappings()
    )
    committed = conn.scalars(
        select(revision_changes.c.revision_id)
        .join(change_proposals, change_proposals.c.id == revision_changes.c.proposal_id)
        .where(change_proposals.c.run_id == run["id"])
        .distinct()
        .order_by(revision_changes.c.revision_id)
    ).all()
    return {
        **{
            key: run[key]
            for key in (
                "id",
                "capture_id",
                "status",
                "config_hash",
                "started_at",
                "completed_at",
                "error",
            )
        },
        "scheduled_at": manifest.get("scheduled_at"),
        "job_id": manifest.get("job_id"),
        "attempt": manifest.get("attempt"),
        "provider": manifest.get("provider", manifest.get("config", {}).get("provider")),
        "inference_performed": manifest.get("inference_performed", False),
        "reference": manifest.get("reference", manifest.get("config", {}).get("reference")),
        "model_provenance": manifest.get("provenance", {}),
        "review_counts": dict(Counter(item["status"] for item in proposals)),
        "committed_revision_ids": committed,
    }


def capture_workflow(services, capture_id):
    repository = services.repository
    capture = repository.capture(capture_id)
    runs = repository.list_runs(capture_id, 1, 0)
    reader = EvidenceReader(services, capture["environment_id"])
    observed = []
    summary = None
    outcome = "unprocessed"
    with repository.engine.connect() as conn:
        head = latest(conn, capture["environment_id"])
        if runs:
            run = runs[0]
            summary = run_summary(conn, run)
            observed = [
                reader.track(state)
                for state in conn.scalars(
                    select(view_track_snapshots.c.state)
                    .where(view_track_snapshots.c.run_id == run["id"])
                    .order_by(
                        view_track_snapshots.c.camera_id, view_track_snapshots.c.view_track_id
                    )
                )
            ]
            counts = summary["review_counts"]
            reference = summary["reference"] or {}
            if run["status"] in {"queued", "running"}:
                outcome = "processing"
            elif run["status"] != "succeeded":
                outcome = "failed"
            elif summary["committed_revision_ids"]:
                outcome = "committed"
            elif reference.get("inspection_reason"):
                outcome = "inspection_only"
            elif reference.get("revision_id") != (str(head["id"]) if head else None):
                outcome = "stale_baseline"
            elif not counts:
                outcome = "no_changes"
            elif counts.get("proposed", 0) + counts.get("needs_review", 0):
                outcome = "pending_review"
            elif counts.get("accepted"):
                outcome = "ready_to_commit"
            else:
                outcome = "review_complete"
    return {
        "capture": capture,
        "source_images": [reader.frame(frame) for frame in capture["frames"]],
        "latest_run": summary,
        "observed_tracks": observed,
        "approved_revision_id": head["id"] if head else None,
        "approved_evidence_path": f"/api/v1/revisions/{head['id']}/evidence" if head else None,
        "outcome": outcome,
    }

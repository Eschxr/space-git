"""Save original rig snapshots once, then start their existing analysis workflow."""

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from scene_tracker.application.captures import CaptureService
from scene_tracker.application.process import ProcessingService
from scene_tracker.application.workflow import run_summary
from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import camera_commits, environments

RIG_SPACE = uuid5(NAMESPACE_URL, "spacegit/local-camera-rig")


class CameraCommitService:
    def __init__(self, services):
        self.services = services
        self.repository = services.repository

    def summary(self, row):
        runs = self.repository.list_runs(row["capture_id"], 1, 0)
        with self.repository.engine.connect() as conn:
            run = run_summary(conn, runs[0]) if runs else None
        return dict(row) | {"run": run, "processing_error": None}

    def list(self, limit, offset):
        with self.repository.engine.connect() as conn:
            rows = list(
                conn.execute(
                    select(camera_commits)
                    .order_by(camera_commits.c.created_at.desc(), camera_commits.c.id)
                    .limit(limit)
                    .offset(offset)
                ).mappings()
            )
        return {"items": [self.summary(row) for row in rows], "limit": limit, "offset": offset}

    def push(self, source_session_id, message, captured_at, uploads):
        ident = uuid5(NAMESPACE_URL, "spacegit/rig-session/" + source_session_id)
        manifest = [
            [
                u.camera_id.value,
                hashlib.sha256(u.data).hexdigest(),
                u.captured_at.isoformat() if u.captured_at else None,
            ]
            for u in sorted(uploads, key=lambda item: item.camera_id)
        ]
        digest = hashlib.sha256(
            json.dumps([message, captured_at.isoformat(), manifest], separators=(",", ":")).encode()
        ).hexdigest()
        # Serialize the default rig history, including uncertain-response retries.
        with self.repository.engine.begin() as lock:
            lock.execute(select(func.pg_advisory_xact_lock(RIG_SPACE.int % (2**63))))
            with self.repository.engine.connect() as conn:
                existing = (
                    conn.execute(
                        select(camera_commits).where(
                            camera_commits.c.source_session_id == source_session_id
                        )
                    )
                    .mappings()
                    .first()
                )
            if existing:
                if existing["request_hash"] != digest:
                    raise AppError(
                        "session_conflict", "This session already has a different commit", 409
                    )
                row = dict(existing)
            else:
                with self.repository.engine.begin() as conn:
                    conn.execute(
                        pg_insert(environments)
                        .values(id=RIG_SPACE, name="Camera rig")
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                try:
                    capture = self.repository.capture(ident)
                except AppError as error:
                    if error.code != "not_found":
                        raise
                    capture = None
                if capture and capture["status"] == "ready":
                    expected = [
                        (u.camera_id.value, hashlib.sha256(u.data).hexdigest(), u.captured_at)
                        for u in sorted(uploads, key=lambda item: item.camera_id)
                    ]
                    actual = [
                        (f["camera_id"], f["sha256"], f["captured_at"]) for f in capture["frames"]
                    ]
                    if actual != expected or capture["captured_at"] != captured_at:
                        raise AppError(
                            "session_conflict",
                            "Saved session bytes or timestamps differ from this retry",
                            409,
                        )
                else:
                    CaptureService(
                        self.repository, self.services.store_factory, self.services.settings
                    ).ingest(RIG_SPACE, captured_at, uploads, capture_id=ident)
                with self.repository.engine.begin() as conn:
                    parent = conn.execute(
                        select(camera_commits.c.id)
                        .where(camera_commits.c.environment_id == RIG_SPACE)
                        .order_by(camera_commits.c.created_at.desc(), camera_commits.c.id)
                        .limit(1)
                    ).scalar()
                    row = dict(
                        conn.execute(
                            insert(camera_commits)
                            .values(
                                id=ident,
                                environment_id=RIG_SPACE,
                                capture_id=ident,
                                source_session_id=source_session_id,
                                message=message,
                                request_hash=digest,
                                parent_id=parent,
                            )
                            .returning(camera_commits)
                        )
                        .mappings()
                        .one()
                    )
            result = self.summary(row)
            if result["run"] is None:
                try:
                    ProcessingService(
                        self.repository, self.services.dispatcher, self.services.settings
                    ).schedule(ident, "default")
                    result = self.summary(row)
                except AppError as error:
                    result["processing_error"] = error.message
            return result

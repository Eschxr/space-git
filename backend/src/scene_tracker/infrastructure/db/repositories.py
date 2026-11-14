"""Transactional domain persistence; PostgreSQL serializes scheduling per capture."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select, update

from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import (
    artifacts,
    captures,
    detections,
    environments,
    frames,
    jobs,
    processing_runs,
)


class Repository:
    def __init__(self, engine):
        self.engine = engine

    def environment(self, environment_id):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(environments).where(environments.c.id == environment_id))
                .mappings()
                .first()
            )
        if row is None:
            raise AppError("not_found", "Environment not found", 404)
        return dict(row)

    def create_environment(self, name, prompts=None):
        with self.engine.begin() as conn:
            return dict(
                conn.execute(
                    insert(environments)
                    .values(name=name, prompts=list(prompts) if prompts else None)
                    .returning(environments)
                )
                .mappings()
                .one()
            )

    def begin_capture(self, environment_id, captured_at):
        self.environment(environment_id)
        capture_id = uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                insert(captures).values(
                    id=capture_id,
                    environment_id=environment_id,
                    captured_at=captured_at,
                    status="uploading",
                    warnings=[],
                )
            )
        return capture_id

    def finish_capture(self, capture):
        with self.engine.begin() as conn:
            for frame in capture.frames:
                conn.execute(
                    insert(frames).values(
                        **frame.model_dump(mode="python"), environment_id=capture.environment_id
                    )
                )
            conn.execute(
                update(captures)
                .where(captures.c.id == capture.id)
                .values(
                    status="ready",
                    source_manifest_hash=capture.source_manifest_hash,
                    warnings=list(capture.warnings),
                )
            )

    def fail_capture(self, capture_id, error):
        with self.engine.begin() as conn:
            conn.execute(
                update(captures)
                .where(captures.c.id == capture_id)
                .values(status="failed", error=error)
            )

    def capture(self, capture_id):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(captures).where(captures.c.id == capture_id)).mappings().first()
            )
            if row is None:
                raise AppError("not_found", "Capture not found", 404)
            result = dict(row)
            result["frames"] = [
                dict(f) | {"role": "overhead" if f.camera_id == "cam_04" else "side"}
                for f in conn.execute(
                    select(frames)
                    .where(frames.c.capture_id == capture_id)
                    .order_by(frames.c.camera_id)
                ).mappings()
            ]
        return result

    def list_captures(self, environment_id, limit, offset):
        self.environment(environment_id)
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(captures)
                    .where(captures.c.environment_id == environment_id)
                    .order_by(captures.c.captured_at, captures.c.id)
                    .limit(limit)
                    .offset(offset)
                ).mappings()
            ]

    def prepare_job(self, capture_id, config, config_hash, retry):
        with self.engine.begin() as conn:
            capture = (
                conn.execute(select(captures).where(captures.c.id == capture_id).with_for_update())
                .mappings()
                .first()
            )
            if capture is None:
                raise AppError("not_found", "Capture not found", 404)
            if capture.status != "ready":
                raise AppError("invalid_capture", "Capture is not ready", 409)
            existing = (
                conn.execute(
                    select(jobs).where(
                        jobs.c.kind == "vision",
                        jobs.c.subject_id == capture_id,
                        jobs.c.idempotency_key == config_hash,
                    )
                )
                .mappings()
                .first()
            )
            if existing and (existing.status != "failed" or not retry):
                return dict(existing)
            run_id = uuid4()
            job_id = existing.id if existing else uuid4()
            attempt = existing.attempt + 1 if existing else 1
            conn.execute(
                insert(processing_runs).values(
                    id=run_id,
                    environment_id=capture.environment_id,
                    capture_id=capture_id,
                    status="queued",
                    config_hash=config_hash,
                    model_manifest={
                        "config": config,
                        "scope": "real_vision_pipeline"
                        if config["provider"] == "real"
                        else "synthetic_fixture_pipeline",
                        "job_id": str(job_id),
                        "attempt": attempt,
                        "inference_performed": False,
                    },
                    progress={"stage": "queued"},
                )
            )
            if existing:
                conn.execute(
                    update(jobs)
                    .where(jobs.c.id == existing.id)
                    .values(
                        run_id=run_id, attempt=existing.attempt + 1, status="queued", error=None
                    )
                )
                job_id = existing.id
            else:
                conn.execute(
                    insert(jobs).values(
                        id=job_id,
                        environment_id=capture.environment_id,
                        kind="vision",
                        subject_id=capture_id,
                        status="queued",
                        idempotency_key=config_hash,
                        run_id=run_id,
                        attempt=1,
                    )
                )
            return dict(conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one())

    def run(self, run_id):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(processing_runs).where(processing_runs.c.id == run_id))
                .mappings()
                .first()
            )
            if row is None:
                raise AppError("not_found", "Processing run not found", 404)
            job = conn.execute(select(jobs).where(jobs.c.run_id == run_id)).mappings().first()
            return dict(row) | {"job": dict(job) if job else None}

    def claim(self, job_id, run_id):
        with self.engine.begin() as conn:
            row = (
                conn.execute(select(jobs).where(jobs.c.id == job_id).with_for_update())
                .mappings()
                .first()
            )
            if not row or row.run_id != run_id or row.status != "queued":
                return False
            conn.execute(update(jobs).where(jobs.c.id == job_id).values(status="running"))
            conn.execute(
                update(processing_runs)
                .where(processing_runs.c.id == run_id)
                .values(
                    status="running", started_at=datetime.now(UTC), progress={"stage": "starting"}
                )
            )
            return True

    def progress(self, run_id, value):
        with self.engine.begin() as conn:
            conn.execute(
                update(processing_runs)
                .where(processing_runs.c.id == run_id, processing_runs.c.status == "running")
                .values(progress=value)
            )

    def finish_job(self, job_id, run_id, status, error=None):
        with self.engine.begin() as conn:
            job = (
                conn.execute(select(jobs).where(jobs.c.id == job_id).with_for_update())
                .mappings()
                .first()
            )
            if not job or job.run_id != run_id or job.status not in {"queued", "running"}:
                return
            conn.execute(update(jobs).where(jobs.c.id == job_id).values(status=status, error=error))
            conn.execute(
                update(processing_runs)
                .where(processing_runs.c.id == run_id)
                .values(
                    status=status,
                    completed_at=datetime.now(UTC),
                    error=error,
                    progress={"stage": status},
                )
            )

    def add_artifact(self, environment_id, run_id, ref):
        with self.engine.begin() as conn:
            conn.execute(
                insert(artifacts).values(
                    id=ref.id,
                    environment_id=environment_id,
                    source_id=run_id,
                    kind=ref.kind,
                    camera_id=ref.camera_id,
                    storage_key=ref.key,
                    sha256=ref.sha256,
                    content_type=ref.content_type,
                )
            )

    def add_detections(self, records):
        if records:
            with self.engine.begin() as conn:
                conn.execute(insert(detections), records)

    def save_manifest(self, run_id, manifest):
        with self.engine.begin() as conn:
            conn.execute(
                update(processing_runs)
                .where(processing_runs.c.id == run_id, processing_runs.c.status == "running")
                .values(model_manifest=manifest)
            )

    def list_detections(self, run_id, camera_id=None, limit=50, offset=0):
        self.run(run_id)
        query = (
            select(detections, frames.c.camera_id)
            .join(frames, detections.c.frame_id == frames.c.id)
            .where(detections.c.run_id == run_id)
        )
        if camera_id is not None:
            query = query.where(frames.c.camera_id == camera_id)
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    query.order_by(frames.c.camera_id, detections.c.id).limit(limit).offset(offset)
                ).mappings()
            ]

    def list_artifacts(self, run_id):
        self.run(run_id)
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(artifacts)
                    .where(artifacts.c.source_id == run_id)
                    .order_by(artifacts.c.storage_key)
                ).mappings()
            ]

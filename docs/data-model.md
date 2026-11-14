# Data model

Phase 1 defines all 17 planned tables as SQLAlchemy Core models in
`backend/src/scene_tracker/infrastructure/db/models.py`. PostgreSQL UUIDs,
timezone-aware timestamps, normal status/key columns and JSONB evidence/metadata
keep domain contracts independent of GPU libraries. Vectors remain external float32
blobs with model/dimension/hash metadata, rather than SQL JSON vectors.

The initial Alembic migration contains frozen PostgreSQL DDL, so future model edits
do not silently change old migrations. Run from `backend/` with `DATABASE_URL` set:

```bash
uv run --no-group vision alembic upgrade head
```

Composite foreign keys scope captures, frames, runs, observations, object links,
proposals, revisions and reconstructions to an environment. Deferred capture
constraints require four distinct canonical camera roles when a capture becomes
ready. Triggers prevent run/frame capture mismatch and observation camera mismatch.
Partial unique indexes allow one active physical-object link per view track and one
root revision per environment. A revision parent can have only one child. Accepted
revision changes must reference proposals from the revision capture. Evidence tables
(frames, detections, revisions, revision changes, snapshots, artifacts) reject SQL
updates and deletes; reviews/link audit lifecycle is implemented in later phases.

Polymorphic references (`jobs.subject_id`, `artifacts.source_id`) require application
ownership checks when those workflows are implemented; they are not foreign keys.
Association candidate endpoints currently refer to view tracks. More detailed
matching behavior is deferred. Durable jobs and review APIs are Phase 2 and later.


Phase 2 migration `0002` adds capture error/warning metadata, processing-run progress,
and the current run ID/attempt on durable jobs. Existing `0001` DDL is unchanged.
Failed runs remain independently queryable after retries, with their logical job ID
and attempt recorded in the run manifest. Schema tests cover full upgrade/downgrade
and re-upgrade through the current head using isolated PostgreSQL schemas.

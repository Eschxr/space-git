# Data model

The original Phase 1 defined 17 planned tables as SQLAlchemy Core models in
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


Phase 3 uses the existing `detections` and `artifacts` tables without a new migration.
A detection stores mask/crop/embedding keys and explicit embedding dimension, dtype,
byte order, model and hash metadata. All blob contents remain in immutable object
storage. Processing manifests retain per-camera contracts, input hashes, fake adapter
source hashes, preprocessing, package versions, timing and error provenance.


Phase 4 migration `0003` adds nullable JSONB `environments.prompts`. In the historical Phase 4 path a null catalogue used deployment prompts. The current
YOLOE path ignores prompts and snapshots only active model assets/settings. Different
versions/configurations create distinct hashes.
No image, prior run, accepted event or revision is overwritten by reprocessing.


## Current refactor additions

There are now **19** application tables. Migration `0004` adds last-seen capture and
missing count to view tracks, run IDs on observations, and immutable
`view_track_snapshots`. Snapshot/observation checks enforce camera, capture/run and
environment consistency. Unique run/track observations prevent duplicate identity
assignments. Mutable registry state is advisory; run snapshots are authoritative.

Migration `0005` preserves old change-type values and adds the six image-view types,
nullable camera/track proposal fields, revision idempotency/hash fields and immutable
`revision_track_snapshots`. Legacy object IDs remain nullable; old object snapshots and
revisions are not rewritten. Database triggers protect committed proposals and revision
snapshots; copied `revision_changes.applied_payload` is the event-history authority.
Environment locks serialize linear commits. Composite foreign keys prevent cross-space
references. Accepted state applies only selected accepted proposals, preserving rejected
history without adopting its changes. No automatic physical-object rows/links are created.

Frozen migration DDL does not import the evolving model metadata. Service tests cover
fresh upgrade/downgrade/re-upgrade and representative legacy event/revision preservation.
Downgrading 0005 with new event types fails rather than deleting/converting those events;
export/backup and explicit operator action are needed before a destructive rollback.
No refactor test migrates or resets the development database.


Phase 5 adds versioned JSON state fields to existing immutable run/revision snapshots:
appearance-prototype references, run identity and snapshot schema version 2. Vectors
stay in immutable binary blobs; source IDs, model, dimension and hash stay in JSON.
Legacy snapshots remain unchanged and derive an optional prototype in memory. Registry
columns remain advisory. No migration beyond 0005 is introduced by Phase 5. New track
history APIs read existing snapshot rows with capture/run order and explicit run status.

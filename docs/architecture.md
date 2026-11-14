# Architecture

The Python 3.11 backend is one modular package: API, core configuration/logging,
domain, application, vision, infrastructure and workers. API imports remain CPU-only
and do not initialize models or connect to infrastructure. Phase 0 exposes liveness.

Later phases use PostgreSQL for durable state, Silo/S3 for immutable originals and
artifacts, and Redis/RQ for JSON-serialized jobs carrying primitive IDs. Workers
resolve data server-side. Database status remains authoritative beyond Redis TTLs.
Vision runs Grounding DINO → SAM 2.1 → DINOv2 outside the API process.

Reconstruction is an independent Python 3.12 uv project, never a backend dependency
or shared workspace member. Future backend scheduling uses the string import path
`reconstruction_worker.worker.run_reconstruction` on a dedicated queue; only the
reconstruction worker resolves it. PointDiT yields per-view PLY, never fused geometry.

Every capture requires exactly cam_01..cam_04, with cam_04 fixed as overhead.
Original bytes remain immutable. Camera-local temporal tracks come first;
cross-view candidates preserve ambiguity and require reviewable, reversible links.
There is no calibration, registration, frontend, OpenUSD or metric movement.

## Phase 1 boundaries

Typed frozen Pydantic contracts cover capture/frame metadata, masks, embedding
metadata, observations/tracks/objects, association candidates, changes, revisions,
jobs and artifacts. The `CameraID` enum derives the role; callers cannot turn
cam_04 into a side view.

`ingest_capture` accepts exactly four image uploads, validates filenames, signature,
MIME, size/pixel limits and timezone-aware timestamps before storing any bytes.
Pillow verifies and decodes JPEG/PNG/WebP; EXIF orientation affects coordinate-frame
dimensions only. Original width, height, orientation, timestamps and SHA-256 remain
available. The returned ready capture includes an ordered source-manifest hash and
skew warnings. No hardware synchronization or calibration is performed. Persisting
uploading/failed/ready state is the Phase 2 orchestration responsibility; a storage
failure currently raises and may leave immutable orphan blobs, never a returned
ready capture. No automatic evidence cleanup is implemented.

Both storage adapters require an environment UUID. Original keys follow the plan's
`originals/{environment_id}/...` layout and reject another environment's prefix.
Derived keys are scoped beneath `environments/{environment_id}/` to prevent collisions
and access across environments. LocalStore atomically publishes one envelope holding
metadata and bytes; it verifies metadata/checksum on reads and rejects overwrites.
It has no HTTP server and explicitly cannot issue signed URLs. S3Store uses signed
conditional PutObject (`If-None-Match: *`) via the MinIO SDK's low-level request method;
idempotent retries require identical bytes and metadata. This avoids a concurrent
check-then-write race. The Phase 1 integration gate passes against PGSTY Silo, the approved
S3-compatible replacement for unavailable MinIO container images. S3 presigned GETs expire in 1–3600 seconds; use a public-endpoint client if the
worker-internal endpoint is not reachable by the downloading client. Storage service
credentials remain trusted server-side configuration, never client inputs.

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
skew warnings. No hardware synchronization or calibration is performed. Phase 2 persists uploading/failed/ready states through CaptureService and the
transactional repository. A storage failure marks the capture failed and may leave
immutable orphan blobs, never a returned ready capture. No automatic evidence cleanup is implemented.

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


## Phase 2 orchestration

Capture APIs persist complete four-frame captures in PostgreSQL and immutable originals
in Silo. RQ jobs use JSON serialization with a versioned dictionary carrying job/run
UUID strings. Queue entries contain no client paths or image bytes. Worker processes
resolve the capture and config from the database; only the worker executes the stage.
The CLI launches SpawnWorker with no GPU initialization in its parent. See
[RQ worker documentation](https://python-rq.org/docs/workers/) for process/serializer behavior.

Logical vision jobs are unique by environment, kind, capture subject and config hash.
Scheduling locks the capture to serialize concurrent requests. Retry reuses the logical
job but creates a new run with retained attempt provenance. Redis receives a unique
job ID per attempt after database commit. Repeated queued requests can redeliver safely;
worker claims are atomic and stale deliveries cannot claim a newer attempt.
PostgreSQL status outlives Redis TTLs. Normal exceptions and RQ failure callbacks
persist failures. Abrupt host loss without callbacks needs future reconciliation.

Phase 2's stage validates the ready capture's four metadata records and completes
orchestration only. Manifests explicitly state `inference_performed: false`. This is
not the fake vision pipeline (Phase 3) or real inference (Phase 4). Real-provider
scheduling is rejected explicitly. Reconstruction scheduling remains deferred.


## Phase 3 fixture pipeline and inspection

Worker-local imports load the pipeline, fake adapters and CPU mask/vector libraries;
API import tests also exclude NumPy and pycocotools. Original bytes are fetched via
server-side storage metadata and checked against frame SHA-256/MIME, then decoded
with EXIF orientation into RGB copies. Fixture PNG metadata is strictly validated
(camera role, bounded object count, unique fixture IDs and in-frame boxes).

Typed DetectionBox, InstanceMask, ObjectEmbedding, PerCameraResult and ProcessingManifest
contracts preserve run/frame/camera IDs, oriented image size and coordinate convention,
and trace IDs. Adapters must return identical aligned detection IDs with matching frame
context. Masks use [COCO compressed RLE](https://github.com/cocodataset/cocoapi/blob/master/common/maskApi.c)
and JSON-safe counts; decoding validates counts before native pycocotools decoding.
Vectors are normalized and persisted as little-endian float32 with explicit metadata.

Cameras are processed in canonical order. Successful outputs and artifacts persist
per camera; camera faults do not stop the remaining views. Each camera gets a result
JSON, including failure details. Final manifests record original hashes, adapter source
hashes, CPU package versions, preprocessing/configuration and timing/errors. Artifacts
are immutable, camera-specific and run-scoped, with corresponding SQL rows. All artifact
logs and result contracts use the run UUID as their correlation ID.

The static report embeds previews and JSON downloads. A deterministic-path ZIP includes
stage artifacts plus the report; runtime timings vary intentionally. There is no browser
application, calibration, association or change processing. Future-stage diagnostic
placeholders explicitly say they are not implemented. The default `fake-fixture`
configuration includes `pipeline_version: fake-v1`, so a prior Phase 2 skeleton-only
success is not silently reused as a Phase 3 result. The old preset name aliases the
new configuration. Failures retry into new run IDs and preserve old evidence.

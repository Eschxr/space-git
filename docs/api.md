# API (Phase 4)

OpenAPI is available at `/openapi.json` and interactive documentation at `/docs`.
The service assumes one local operator without authentication. Bind to loopback.
`GET /health/live` returns `{"status":"ok"}`; it does not probe services or models.

| Method | Route | Behavior |
|---|---|---|
| POST | `/api/v1/environments` | JSON `{ "name": "room" }`; returns 201 with UUID |
| POST | `/api/v1/environments/{id}/captures` | Four-file multipart ingestion; returns 201 |
| GET | `/api/v1/environments/{id}/captures` | Capture summaries, `limit` (1–100, default 50) and `offset` (default 0) |
| GET | `/api/v1/captures/{id}` | Capture status, timestamps, warnings/errors and frames |
| POST | `/api/v1/captures/{id}/process` | JSON `{ "preset": "fake-fixture", "retry": false }`; returns 202 with run and job |
| GET | `/api/v1/processing-runs/{id}` | Durable status, progress, manifest, timing and errors |

## Capture uploads

All four file fields are required exactly once: `cam_01`, `cam_02`, `cam_03`,
`cam_04`. Filenames must match roles (for example `cam_01.jpg`); supported formats
are JPEG, PNG and WebP with matching signature, extension and MIME. `cam_04` always
reports `role: "overhead"`. Unknown/duplicate fields or roles are rejected with 422.
Optional text fields: `captured_at` (logical timestamp), and `cam_01_captured_at`
through `cam_04_captured_at`. All supplied timestamps require timezone offsets.
The logical timestamp defaults to current UTC; absent frame timestamps remain null.
Skew exceeding `MAX_TIMESTAMP_SKEW_SECONDS` produces a warning.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/environments \
  -H 'Content-Type: application/json' -d '{"name":"room"}'
# Replace ENVIRONMENT_ID with the returned UUID:
curl -X POST http://127.0.0.1:8000/api/v1/environments/ENVIRONMENT_ID/captures \
  -F cam_01=@cam_01.jpg -F cam_02=@cam_02.jpg \
  -F cam_03=@cam_03.jpg -F cam_04=@cam_04.jpg \
  -F captured_at=2026-11-14T12:00:00Z
```

A capture is persisted as `uploading` before image validation/storage. Its four frame
rows and `ready` state are finalized atomically; failures persist `failed` with an
error. Structural multipart errors are rejected before allocating a capture.
Image/storage failures return a `capture_id` for inspection. Already written orphan
originals are retained on failure. No evidence is overwritten or automatically deleted.
Repeated uploads currently create separate captures; upload deduplication is deferred.

Per-file limits are `MAX_IMAGE_BYTES` (default 20 MiB) and `MAX_IMAGE_PIXELS` (40M).
The API also caps total request bytes at four file limits plus 64 KiB multipart
allowance, including chunked uploads. Total size errors use 413; per-image validation
errors use 422. Original bytes and SHA-256 are retained; dimensions reflect EXIF-corrected
coordinates alongside original dimensions/orientation.

## Processing and retry

```bash
curl -X POST http://127.0.0.1:8000/api/v1/captures/CAPTURE_ID/process \
  -H 'Content-Type: application/json' -d '{"preset":"fake-fixture"}'
curl http://127.0.0.1:8000/api/v1/processing-runs/RUN_ID
# After a failed run:
curl -X POST http://127.0.0.1:8000/api/v1/captures/CAPTURE_ID/process \
  -H 'Content-Type: application/json' -d '{"preset":"fake-fixture","retry":true}'
```

Phase 3 defaults to `fake-fixture` with `VISION_PROVIDER=fake`; `skeleton` is a
compatibility alias. Both resolve to the same versioned pipeline configuration hash.
A successful run stores fixture-derived detections, COCO compressed RLE masks,
normalized fake float32 embeddings and debug artifacts. Its manifest states
`scope: "synthetic_fixture_pipeline"` and `inference_performed: false`. These are
synthetic contract outputs, with no trained models executed. PNG fixture metadata
controls boxes/appearance seeds; images without it produce zero detections and a
warning. Real-provider requests require verified local assets before enqueueing; see below.
Generate fixtures with `scene-tracker synthetic-capture --output DIR`.

Processing is idempotent by `(kind, capture, config hash)` with a database uniqueness
constraint and per-capture scheduling lock. Identical requests reuse one logical job
and current run. `retry: true` after failure creates a new run and increments the job
attempt, preserving earlier run records/errors. Old run responses may have `job: null`
after a retry; their manifest retains the logical job ID and attempt. Repeated requests
for queued work reattempt delivery with a unique Redis job ID, covering an interrupted
delivery after the database commit. Worker claims guard against duplicate/stale deliveries.
A queue error persists failed state and returns `queue_unavailable` with job/run IDs.

States are `queued → running → succeeded | failed`. PostgreSQL is authoritative even
if Redis results expire. Request handlers only enqueue; the test dispatcher is drained
explicitly outside request handlers. Ordinary worker exceptions and RQ failure callbacks
persist failure. Automatic reconciliation of a worker host killed without callbacks is
deferred; such a job can remain `running` and needs operator investigation.

Application errors use `{"error":{"code":"...","message":"..."}}` with optional
capture/job/run IDs. Codes include `invalid_capture`, `not_found`, `storage_unavailable`,
`queue_unavailable`, `model_unavailable`, `upload_too_large`. FastAPI payload/schema
validation retains its standard 422 `detail` response. Responses include an
`X-Correlation-ID` request trace header; run/job IDs provide worker traceability.


## Detections and inspection bundles

- `GET /api/v1/processing-runs/{id}/detections` returns a typed detection page, with
  optional `camera_id=cam_01..cam_04`, `limit` (1–100) and `offset`. Each row preserves
  run/frame/camera IDs, oriented pixel boxes, mask/crop keys and embedding metadata.
  Binary embeddings are little-endian float32 blobs with explicit dimension/model/hash.
- `GET /api/v1/processing-runs/{id}/debug` returns the stored manifest and typed artifact
  rows with short-lived signed GET URLs. Artifacts carry camera IDs, source run IDs,
  SHA-256 and a run correlation ID. Includes masks, embeddings, crops, per-camera
  boxes/mask overlays, crop sheets, JSON results, manifest, standalone report and ZIP.

The report embeds its images and downloadable JSON evidence so a single downloaded
HTML file works offline and through a private signed URL. It is a static inspection
artifact, not a frontend application. The ZIP includes all run derivatives except
itself. The root manifest indexes stage artifacts; the debug API lists the final
manifest/report/bundle artifacts as well, avoiding self-referential checksums.
Runtime timing values vary; fixture geometry, masks, vectors, ordering and colors
are deterministic for the same input/context. Each new run has separate IDs and keys.

Per-camera adapter errors produce an explicit failed camera result and manifest entry.
Other cameras still run, and successful camera outputs remain queryable. The run/job
is marked failed after writing available inspection diagnostics. An explicit retry
uses a new run and never overwrites the old output or originals. A global storage
outage can prevent saving the report itself; the database still records job failure.

`temporal_matches.json`, `cross_view_candidates.json` and `change_proposals.json`
are placeholders with `implemented: false`, planned phase numbers and empty item
lists. They do not claim matching or change detection has run. No object identities
are invented; overlays show view tracks as unassigned and physical objects as unlinked.


## Real-provider configuration (Phase 4)

Environment creation accepts optional `prompts: ["chair", "table", ...]`; responses
return the stored catalogue (null means use `VISION_PROMPTS` defaults). This catalogue
is used by the real detector. Labels alone are not object identity, and a closed
catalogue cannot guarantee extraction of unseen types.

Set `VISION_PROVIDER=real` in server configuration and use processing preset `default`.
The server snapshots environment prompts, thresholds, model names, absolute checkpoint
paths/hashes, BERT directory fingerprint, source commits/config hashes and device.
Before enqueueing it runs local file/source/hash preflight without importing Torch.
Its `files_verified_runtime_unprobed` result does not claim GPU readiness. The worker
re-verifies that assets match the snapshot, imports only pinned local sources and loads
all three models once for its four frames. Model/dependency/device failures produce
explicit `model_unavailable` errors, with no fake adapters used in real mode.

Real results use `scope: real_vision_pipeline` and `provider: real`. Their manifest's
`inference_performed` flag records whether a real-provider detector call completed;
per-camera statuses/errors show which stages finished. This flag is execution provenance,
not accuracy certification. The same mask/vector/artifact APIs apply, now including
`detector_candidates.json` with kept/suppressed/rejected raw-query evidence. Thresholds
and NMS do not automatically resolve physical-object identities. See
[model setup and manual smoke](model-setup.md) for exact commands and current validation limits.

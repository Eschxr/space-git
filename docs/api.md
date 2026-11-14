# API (Phase 2)

OpenAPI is available at `/openapi.json` and interactive documentation at `/docs`.
The service assumes one local operator without authentication. Bind to loopback.
`GET /health/live` returns `{"status":"ok"}`; it does not probe services or models.

| Method | Route | Behavior |
|---|---|---|
| POST | `/api/v1/environments` | JSON `{ "name": "room" }`; returns 201 with UUID |
| POST | `/api/v1/environments/{id}/captures` | Four-file multipart ingestion; returns 201 |
| GET | `/api/v1/environments/{id}/captures` | Capture summaries, `limit` (1–100, default 50) and `offset` (default 0) |
| GET | `/api/v1/captures/{id}` | Capture status, timestamps, warnings/errors and frames |
| POST | `/api/v1/captures/{id}/process` | JSON `{ "preset": "skeleton", "retry": false }`; returns 202 with run and job |
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
  -H 'Content-Type: application/json' -d '{"preset":"skeleton"}'
curl http://127.0.0.1:8000/api/v1/processing-runs/RUN_ID
# After a failed run:
curl -X POST http://127.0.0.1:8000/api/v1/captures/CAPTURE_ID/process \
  -H 'Content-Type: application/json' -d '{"preset":"skeleton","retry":true}'
```

Phase 2 supports `skeleton` with `VISION_PROVIDER=fake` only. It verifies orchestration
and four-frame metadata, then completes with manifest `scope: "orchestration_only"`
and `inference_performed: false`. There are no detections, masks or embeddings yet;
Phase 3 implements the fake pipeline and Phase 4 real adapters. `VISION_PROVIDER=real`
returns explicit `model_unavailable` without fake fallback.

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

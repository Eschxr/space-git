# API — YOLOE image-view history

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

Processing defaults to `fake-fixture` with `VISION_PROVIDER=fake`; `skeleton` is a
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

`temporal_matches.json` and per-camera `matches.json` contain chosen references,
candidate terms, unresolved alternatives and durable camera-local track IDs.
`change_proposals.json` and changes overlays contain provisional image-view events.
Cross-view association remains optional and explicitly unimplemented. Detections now
include nullable `view_track_id`; physical-object links are never assigned automatically.

## Real-provider configuration

Set `VISION_PROVIDER=real`, `VISION_EXTRACTOR=yoloe` and use preset `default`.
Supply the exact local YOLOE prompt-free checkpoint/hash and pinned DINOv2 source/weights;
[model setup](model-setup.md) contains all commands. Legacy environment `prompts`
remain readable/accepted but are ignored. No text encoder or `set_classes()` is used.
The API verifies local hashes/source and snapshots paths/settings; the worker rechecks
and loads YOLOE+DINOv2 in its spawned job child. Missing assets/device/dependencies
fail explicitly, with no fake fallback. Model provenance is execution evidence,
not a quality certification. `inference_performed` records a completed real extractor
call; inspect per-camera status for later errors.

## Proposed changes, review and revision commits

| Method | Route | Behavior |
|---|---|---|
| GET | `/api/v1/processing-runs/{id}/changes` | Proposed/accepted/rejected events; camera/track IDs, before/after refs and signed evidence URLs; limit 1–1000, offset |
| POST | `/api/v1/change-proposals/{id}/decision` | `{ "status": "accepted" or "rejected" or "needs_review", "reason": "optional" }` |
| POST | `/api/v1/environments/{id}/revisions` | Commit selected accepted proposals from one succeeded capture/run |
| GET | `/api/v1/environments/{id}/revisions` | Newest-first revision page, limit 1–100, offset |
| GET | `/api/v1/revisions/{id}` | Immutable revision metadata and approved camera-local track states |
| GET | `/api/v1/revisions/{id}/diff` | Events against parent; optional ancestor `from_revision_id` |
| GET | `/api/v1/captures/{id}/highlights` | Required camera_id, optional revision_id; canonical source-image regions |

Changes are `appeared_in_view`, `moved_in_view`, `appearance_changed`,
`missing_from_view`, `reappeared`, `uncertain`. They describe visible evidence;
missing does not mean physically removed and label agreement is not identity.
The first capture has initial appeared observations and no false moves. Review and
commit those to establish an approved baseline. Empty scenes have processed state;
this MVP's commit requires a nonempty selection. No cross-view merge is required.

```bash
curl http://127.0.0.1:8000/api/v1/processing-runs/RUN_ID/changes
curl -X POST http://127.0.0.1:8000/api/v1/change-proposals/PROPOSAL_ID/decision \
  -H 'Content-Type: application/json' -d '{"status":"accepted"}'
curl -X POST http://127.0.0.1:8000/api/v1/environments/ENVIRONMENT_ID/revisions \
  -H 'Content-Type: application/json' \
  -d '{"capture_id":"CAPTURE_UUID","proposal_ids":["ACCEPTED_PROPOSAL_UUID"],"idempotency_key":"review-001","message":"Initial baseline"}'
curl http://127.0.0.1:8000/api/v1/revisions/REVISION_ID/diff
curl 'http://127.0.0.1:8000/api/v1/captures/CAPTURE_ID/highlights?camera_id=cam_01&revision_id=REVISION_ID'
```

A commit copies selected accepted event payloads and applies their camera-local states
to the prior approved snapshot atomically. Rejected/unselected proposals remain
queryable and do not alter that baseline. Identical repeated commits with the same
key return the same revision (201); different contents with the key return 409.
Previously committed proposals cannot be changed or committed again. Stale accepted
baselines return 409; reprocess to review against the new parent. Changed processing
configurations create new run IDs and never alter old detections/revisions.

`reference_capture_id` on process requests is an optional same-environment, earlier
processed capture for debugging. Otherwise association prefers eligible approved track
state, then latest processed evidence. All chosen references and scores persist in
tracking JSON. Manual debug baselines cannot silently replace the accepted parent.

Revision diffs return before/after boxes, canonical masks, crop and image URLs on
image-view events. URLs are freshly signed and expire; their changing signatures do
not change the underlying immutable event. A diff reference must be an ancestor.
Historical physical-object payloads remain readable; no view-track mapping is invented.

Highlights default to **committed accepted** events only. Query both source captures
with the same revision to retrieve before and after movement regions separately.
Missing events only highlight the last-visible capture, never the empty current view.
A missing mask is explicit, not a fabricated region. Other-environment revisions fail.
See [highlight contract and synthetic exports](highlights.md) and
[matching thresholds/review semantics](matching-and-diffs.md).

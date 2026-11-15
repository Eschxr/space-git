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


## Camera-local track history (Phase 5)

- `GET /api/v1/view-tracks/{id}` returns camera/environment, first-seen time,
  advisory registry status, last-seen capture and missing count. Unknown IDs return 404.
- `GET /api/v1/view-tracks/{id}/history?limit=50&offset=0` returns immutable run snapshots
  in capture-time/run-start/ID order; limit is 1–100. Each item includes run/capture,
  run status, camera, lifecycle state, match evidence and appearance-prototype refs.
  Registry fields may advance; snapshot contents do not. Failed/running run snapshots
  are explicitly tagged by `run_status`, not described as succeeded or approved.

History is observational run history, separate from accepted revision history. A
prototype is a reference to the last confidently associated stored embedding, with
source capture/frame/detection/camera and hash/model metadata. It survives a missing
mask/vector or missed observation; it does not fabricate a vector for that frame.
Candidates trace the actual appearance reference used for comparison.

`temporal_matches.json` now has schema version 2, including per-camera candidate costs,
term contributions, gate/reject reasons, top-two valid scores/margins, eligible counts,
chosen assignments and unmatched decisions. Accepted baselines use reference kind
`accepted_revision` and its revision ID; they can combine several source runs, so a
single `reference_run_id` is not claimed for those comparisons. Historical v1 artifacts
remain readable. The processing version changed so old successful results are preserved
and not reused as version-2 tracking output.

## Capture workflow and processing attempts

All paths below use the existing loopback API and the `/api/v1` prefix.

| Method | Path | Response |
|---|---|---|
| GET | `/captures/{id}/processing-runs` | Newest-first attempts, provider, job/attempt, timestamps, config hash, model provenance, frozen reference, review counts and committed revision IDs |
| GET | `/captures/{id}/workflow` | Four source images with signed evidence, latest attempt, observed tracks, approved head and an actionable outcome |
| GET | `/change-proposals/{id}/decisions` | Append-only review decisions and current proposal status/reason |
| GET | `/revisions/{id}/evidence` | Versioned provenance, four source images, all approved tracks and signed image/mask/crop/overlay evidence |
| GET | `/revisions/{id}/compare?from_revision_id=UUID` | Approved endpoint state comparison |
| GET | `/view-tracks/{id}/revisions` | Accepted revision changes for one camera-local identity |

Attempt, decision and accepted-track lists support `limit=1..100` and `offset>=0`.
Workflow outcomes include `unprocessed`, `processing`, `failed`, `pending_review`,
`ready_to_commit`, `review_complete`, `committed`, `no_changes`, `inspection_only`
and `stale_baseline`. Zero proposals need no commit. All-rejected proposals leave
the approved state at its current head. Commits require at least one accepted proposal.
After a partial commit, reprocess to review remaining proposals against the new head.

### Reference policy

Scheduling holds the environment lock and records a single reference for all four
views in the config hash. It prefers the latest eligible approved revision, whose
tracks may retain observations from multiple source captures. Without an approved
baseline it uses the latest eligible succeeded tracked run from another capture.
Future captures and unsuccessful runs are excluded. Ties use run IDs after capture
and completion times. A new baseline creates a new processing configuration.

A queued run keeps its recorded reference even when the head advances before the
worker starts. Its later commit fails with `stale_baseline` if the approved parent
has advanced. Reprocessing creates proposals against the new head.

Reprocessing a capture already at the approved head compares against that head and
is marked `approved_capture_rerun` for inspection. Backdated captures compare against
eligible older evidence and are marked `backdated_capture` when the current head is
newer. Explicit `reference_capture_id` requests require a succeeded tracked earlier
capture and are marked `explicit_reference`. These inspection runs return 409
`inspection_only` on commit and remain discoverable with earlier attempts.

### Review decisions

The decision POST accepts the existing `status` and `reason`, plus optional
`reviewer` (default `local-operator`) and `idempotency_key`. The reviewer is an
operator-supplied label in this local application. Each decision retains previous/new
status, previous/new reason, label and UTC time. An identical keyed retry returns the
recorded decision and current proposal status. Reusing its key with different content
returns 409. Retrying an earlier key after a newer review leaves the newer status in
place. Without a key, an exact repeat of the latest decision reuses that record.
Concurrent decisions serialize on the proposal.

Accepting `uncertain` approves the proposal's camera-local run snapshot, including
its uncertainty flag, assigned track IDs and candidate evidence. Accepting a missing
event applies an unobserved state with last-visible evidence. Repeated accepted missing
events advance its missing counter. Reappearance applies the newly observed state and
resets that counter. Rejection or needs-review leaves approved state at its previous
snapshot. Committing copies the selected event and final review record. Committed
events and decision history reject database modification.

### Revision evidence and comparisons

`GET /revisions/{id}` preserves raw approved `tracks` and adds a stable
`evidence_path`. The linked response separates `source_images` from
`approved_tracks`. Source images belong to the revision capture. An approved track
can reference an older capture when a newer observation was rejected. Each observation
supplies its capture/frame/run/camera, canonical dimensions, box, image, mask, crop and
annotated overlays. Render each observation against its referenced image. Overlays
describe the associated processing run.

New commits snapshot source frames, run manifests, model/config provenance and immutable
artifact keys/hashes inside the revision transaction. Legacy revisions return
`origin=derived_legacy` provenance assembled from retained events and runs. Signed
URLs are generated on read. Unavailable blobs retain their key/hash and an explicit
unavailable reason, allowing the remaining evidence to be inspected.

The existing `/diff` route returns committed events along an ancestor chain.
`/compare` compares endpoint track content in deterministic camera/track order,
with `added`, `removed`, `missing`, `restored`, `changed` or `unchanged`
entries and before/after evidence. Compared fields are lifecycle status, raw label,
normalized box rounded to six decimals, mask content hash, embedding hash and
uncertainty. Capture/run IDs, missing counters and timestamps do not affect net content.
Movement out and back can have an unchanged endpoint alongside both move events.

Identical comparisons return unchanged entries. Reverse comparisons swap evidence and
report `direction=reverse`. A track absent from the earlier endpoint is added, and
the reversed comparison reports removed from that endpoint state. Unrelated or
cross-environment revisions return 422. Unknown IDs return 404. Accepted track history
lists revisions that committed an event for that track, with prior/approved snapshots
and reviewed events.

### HTTP walkthrough

After upload and processing, discover the latest state and review operator-selected
proposals. Commit the selected accepted IDs with the revision POST documented above.

```bash
curl http://127.0.0.1:8000/api/v1/captures/CAPTURE_ID/processing-runs
curl http://127.0.0.1:8000/api/v1/captures/CAPTURE_ID/workflow
curl -X POST http://127.0.0.1:8000/api/v1/change-proposals/PROPOSAL_ID/decision \
  -H 'Content-Type: application/json' \
  -d '{"status":"accepted","reviewer":"operator","reason":"Reviewed evidence","idempotency_key":"review-001"}'
curl http://127.0.0.1:8000/api/v1/change-proposals/PROPOSAL_ID/decisions
curl http://127.0.0.1:8000/api/v1/revisions/REVISION_ID/evidence
curl 'http://127.0.0.1:8000/api/v1/revisions/REVISION_ID/compare?from_revision_id=EARLIER_REVISION_ID'
curl http://127.0.0.1:8000/api/v1/view-tracks/TRACK_ID/revisions
```

The frontend can consume these versioned contracts through a Scene Tracker adapter.
Its existing edge `/commits`, metric wall scenes and branch/merge operations have
different contracts. Revision evidence links per-source-capture/camera highlight
manifests. A future PointDiT viewer must use the matching capture/frame/camera and
recorded pixel-to-point transform for each cloud. The current projection UI can
independently open local PLY assets. Phase 9 supplies reconstruction jobs and cloud
artifact transport.

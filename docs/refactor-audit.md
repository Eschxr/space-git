# R0 — Phase 4 implementation audit and refactor baseline

Baseline: `bb92e09` (`feat: integrate real vision adapters behind stable contracts`).
Authority: `CODEX_YOLOE_REFACTOR_PLAN.md` supersedes older vision/tracking instructions
after Phase 4. Execute R0–R6, stopping at each checkpoint, before future PointDiT P9.
This is an audit and proposed change map, not a YOLOE implementation or model validation.

## Baseline integrity and scope

Before edits, both `git diff --exit-code` and `git diff --cached --exit-code` passed.
`git status --short` showed only the user-supplied `CODEX_YOLOE_REFACTOR_PLAN.md` and
existing `frontend/` directory as untracked. Thus tracked/staged content was clean;
the whole working tree was not empty of untracked files. The plan is retained verbatim;
frontend files remain untouched. R0 changes only instructions/audit/status documents.
No inference code, dependencies, lockfiles, migrations, original images or existing
application rows were modified. Tests created and cleaned their own isolated data.
No production/development schema was reset or migrated. Application data contents
were not inventoried, so this audit does not assume historical rows are absent.

## What is actually implemented

Python 3.11 backend with four-role ingestion, immutable originals, PostgreSQL state,
Silo S3 storage, JSON Redis/RQ jobs, fake/real extraction interfaces, DINOv2 and debug
artifacts. Real extraction currently requires Grounding DINO, SAM 2.1 and local BERT.
The fake pipeline reads explicit synthetic PNG metadata and emits rectangle masks and
eight-dimensional hash vectors. Real DINOv2 emits normalized 384-dimensional vectors.

No YOLOE adapter or ObjectExtractor protocol exists. There is no implemented temporal
matching, track lifecycle, semantic proposer, review/commit/diff/highlight API or PointDiT
execution. The SQL/domain definitions for several of these exist, but are not application
workflows. Tracking/change debug JSONs explicitly say `implemented: false`; overlays
show unassigned tracks/unlinked physical objects. Do not treat those files as completed
tracking or empty, experimentally verified change results.

## Existing endpoints — verified from generated OpenAPI

All versioned routes live in `backend/src/scene_tracker/api/routes/captures.py`.

| Method | Actual path | Handler / response |
|---|---|---|
| POST | `/api/v1/environments` | `create_environment`; EnvironmentResponse, optional legacy prompts |
| POST | `/api/v1/environments/{environment_id}/captures` | `upload_capture`; CaptureResponse; four unique multipart roles |
| GET | `/api/v1/environments/{environment_id}/captures` | `list_captures`; CapturePage, limit/offset |
| GET | `/api/v1/captures/{capture_id}` | `get_capture`; CaptureResponse |
| POST | `/api/v1/captures/{capture_id}/process` | `process`; RunResponse, 202 |
| GET | `/api/v1/processing-runs/{run_id}` | `get_run`; RunResponse |
| GET | `/api/v1/processing-runs/{run_id}/detections` | `get_detections`; DetectionPage, camera filter/limit/offset |
| GET | `/api/v1/processing-runs/{run_id}/debug` | `get_debug`; DebugResponse, manifest/artifacts/signed URLs |
| GET | `/health/live` | `api/main.py:live`; process liveness only |

Framework routes: GET `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`.
There is no `/health/ready`, associations/objects/changes route, proposal decision route,
revision route, highlights route, reconstruction route or generic artifact download route.
The older plan/refactor examples describe future routes, not existing endpoints to rename.

## Existing data and adapter contracts

All base domain Contract models are frozen, reject extra fields and nonfinite floats.

| File | Existing names and relevant fields |
|---|---|
| `domain/enums.py` | CameraID (`cam_01..04`; cam_04 role overhead), CaptureStatus, JobStatus, ReviewStatus, TrackStatus, ChangeType. ChangeType still uses added_candidate/moved_2d_candidate/appearance_changed_candidate/unobserved/removed_candidate/possible_relocation/unchanged. |
| `domain/contracts.py` | Contract, SHA256, Score; Frame (capture/camera/key/hash, oriented/original dimensions, EXIF, timestamp/MIME), Capture (four ready frames, manifest hash/warnings), Mask (`size=(height,width)`, text counts, coco_compressed_rle), EmbeddingMetadata (key/dimension/float32/model/hash/normalization), Detection (run/frame/camera, label/score/xyxy, optional mask and embedding). |
| `domain/contracts.py` | ViewTrack, PhysicalObject, ChangeProposal, Revision, Job, Artifact, ProcessingRun, TrackObservation, ObjectTrackLink, AssociationCandidate, Reconstruction. These are DTOs; only capture/job/vision persistence is wired. ChangeProposal.object_id is already optional; Revision and object snapshots currently assume object-oriented accepted state. |
| `vision/contracts.py` | FrameContext (run/frame/camera, dimensions, trace, oriented_rgb_pixel_xyxy); DetectionBox (UUID, required fixture_id tag, label/score, integer xyxy); InstanceMask (detection_id, RLE, score); ObjectEmbedding (detection_id, normalized values/dimension/dtype/model); ArtifactRef; PerCameraResult; ProcessingManifest (schema 1, provider/scope/config/provenance/sources/timing/errors/job/attempt). |
| `vision/contracts.py` | Detector.detect(rgb, prompts, config), Segmenter.segment(rgb, boxes, config), Embedder.embed(rgb, masks, boxes, config). Current config is a tuple containing FrameContext and fixture metadata/None. No combined ObjectExtractor exists. |
| `api/schemas/captures.py` | EnvironmentCreate, EnvironmentResponse, FrameResponse, CaptureSummary, CaptureResponse, CapturePage, ProcessRequest, JobResponse, RunResponse, DetectionResponse, DetectionPage, DebugArtifact, DebugResponse. ProcessRequest accepts preset fake-fixture/skeleton/default and retry; no reference_capture_id yet. |
| `infrastructure/storage/base.py` | Blob(key, sha256, content_type, size), StorageError, ArtifactStore.stat/put/get/presign. LocalStore stores atomic immutable metadata+bytes envelopes and cannot presign; S3Store conditionally puts immutable objects and presigns GETs. |
| `infrastructure/queue/base.py` | JobDispatcher.enqueue_vision(job_id, run_id, attempt), enqueue_reconstruction(job_id); reconstruction method raises NotImplementedError. InlineDispatcher queues until explicitly drained. |
| `reconstruction_worker/contracts.py` | ReconstructionJob TypedDict(schema_version: int, reconstruction_id: str), a scaffold, not a highlight or point-map contract. |

OpenAPI additionally emits CameraID, CaptureStatus, JobStatus, HTTPValidationError and
ValidationError schemas. No Ultralytics tensors/results are currently stored or imported.

## Execution, evidence and persistence map

- `application/ingest.py` / `captures.py`: validate all four role-labelled JPEG/PNG/WebP
  images, byte/pixel limits, MIME/signature and timestamps; EXIF-corrected dimensions;
  preserve received bytes and SHA-256; uploading → ready/failed persistence. Retain.
- `application/process.py`: real preflight requires all old model sources/checkpoints/BERT,
  snapshots environment/deployment prompts/settings/assets, hashes config, schedules jobs.
  This is a primary R1 cut point; changing runtime alone would leave the old prerequisites.
- `workers/jobs.py`, `workers/vision.py`, `infrastructure/queue/rq.py`: worker claims durable
  jobs, resolves IDs/config server-side, rechecks assets and loads real models inside a
  spawned child. RQ uses JSONSerializer, versioned primitive IDs, unique job ID per attempt,
  failure callback, timeout 3600s and result TTL 300s. PostgreSQL status is authoritative.
  Retry reuses the logical job but creates a separate processing run. Preserve boundaries.
- `vision/runtime.py`: imports verified local upstream packages, builds Grounding DINO +
  local BERT, SAM 2.1 and DINOv2. Replace normal extractor initialization in R1; retain
  DINOv2 loading/checkpoint choice. No automatic model downloads are implemented.
- `application/vision_pipeline.py`: canonical camera order; separate detect → segment →
  embed calls; strict box/mask/vector ID and context alignment; writes per-camera
  detections/artifacts/results, continues after camera faults, records manifest/errors.
  Current strict zip/cardinality rules assume every detection has a mask AND embedding.
- `vision/preprocessing.py`, `masks.py`, `embeddings/dinov2.py`: verify original hashes/MIME,
  EXIF transpose to RGB, checked compressed COCO RLE, padded masked square crops at 224px,
  gray-127 background, ImageNet normalization, batched 384-D CLS output + L2 validation.
  Retain DINOv2 and its model choice; extend missing/tiny-mask behavior in R2.
- `vision/debug/overlays.py`, `report.py`: deterministic colors/labels, masked crops/sheets,
  per-camera previews, standalone embedded-image HTML and ZIP. Root manifest avoids
  self-referential checksums; debug API lists final artifacts. Extend, do not replace.
- `infrastructure/db/repositories.py`: environment/capture methods, locked job creation/
  claim/finish, progress/manifests, add/list detections and artifacts. No tracking/revision
  repository methods exist. Camera ID/dimensions come through frames, not detection columns.
- `infrastructure/storage/*`: originals use `originals/{environment_id}/{capture_id}/...`;
  derivative logical keys use `vision/{run_id}/...`, scoped physically beneath
  `environments/{environment_id}/`. Masks are JSON RLE; vectors are little-endian `.f32`
  blobs with dimension/model/hash metadata; crops/overlays PNG. Keep old keys and evidence.
- `infra/compose.yaml`: PostgreSQL 16, Redis 7, approved pinned PGSTY Silo and bundled-mcli
  private-bucket bootstrap, loopback ports/named volumes. Silo superseded unavailable
  MinIO images (ADR 0002); do not revert storage as part of the YOLOE refactor.

## SQL schema and incompatibilities

`infrastructure/db/models.py` defines 17 tables: environments, captures, frames,
processing_runs, detections, view_tracks, physical_objects, track_observations,
object_track_links, association_candidates, change_proposals, revisions,
revision_changes, object_state_snapshots, jobs, reconstructions, artifacts.

Migration chain: `0001_initial` (frozen PostgreSQL DDL for all tables, indexes and
integrity/immutability triggers) → `0002_orchestration` (capture warnings/errors,
run progress, job current run/attempt) → `0003_environment_prompts` (nullable JSONB prompts).
Never edit or rerun these migrations against an existing database as a reset.

Important constraints to preserve/extend deliberately:

- Ready captures require four unique canonical camera roles. Frames, detections,
  artifacts, revisions, revision_changes and object_state_snapshots reject updates/deletes.
- Composite environment foreign keys protect most associations; an observation trigger
  checks camera/capture against its detection/track. Detection ID assignment is unique.
  Association candidates currently reference TWO view tracks, not track-to-detection pairs.
- change_proposals.object_id is nullable, but its type CHECK allows only old ChangeType
  values. New view-local events cannot be inserted until that constraint is extended.
- object_state_snapshots.object_id is nonnullable and physically object-scoped. It cannot
  represent a mandatory view-track-only accepted baseline without creating fake objects.
- Revision inserts require accepted proposals from the revision capture; one root per
  environment/one child per parent and unique committed proposal prevent some duplicates.
  R4 still needs atomic commit/idempotency and immutable before/after snapshot behavior.
- Existing tracking tables lack last-seen/missing-count/versioned per-run track snapshots.
  This audit does not assume manually inserted historical track/revision rows are absent.

Chosen minimal additive schema strategy (design only; no R0 migrations):

| Checkpoint | Planned change |
|---|---|
| R1–R2 | No extraction-table migration by default: label/score/JSONB xyxy, nullable mask_key/embedding_key/metadata, frame dimensions/orientation, artifact rows and run JSONB already fit YOLOE. Preserve prompts column as nullable legacy metadata; do not require/read it on the new path. Store explicit inference transform in run/camera/artifact metadata; derive optional normalized boxes in responses. |
| R3 | Add last_seen_capture_id (nullable scoped FK) and missing_count (nonnegative default) to view_tracks. Add nullable run_id to track_observations for versioned/new observations and a partial unique (run_id, view_track_id) constraint for nonnull runs; retain existing detection uniqueness and add an explicit scoped detection FK. Use existing artifact storage for complete scored track→detection candidate reports; do not repurpose the two-track association_candidates table. Persist missing/unobserved state snapshots per run in a small new view_track_snapshots table keyed by run/track with environment/camera/reference refs and JSONB state. No physical-object rows required. |
| R4 | Add nullable camera_id and view_track_id to change_proposals with scoped/camera validation; use existing before_ref/after_ref/evidence JSONB for masks, detection/capture/frame IDs, confidence, displacement and debug refs. Extend the type CHECK to accept the six new view events AND all legacy values; preserve existing rows unchanged. Add revision_track_snapshots keyed by revision/track for accepted per-camera state, leaving legacy object_state_snapshots intact. Add nullable environment-scoped unique revision idempotency_key for new commits. Keep existing linear/accepted-event integrity constraints. |
| R5 | No new table by default: derive accepted per-camera highlight JSON from revision changes + track snapshots + exact source frame/mask refs. Use artifacts for fake colored PLY/sidecars and explicit image→grid transforms. Missing-from-view highlights reference the prior capture; never invent a current mask. |

Future checkpoints must test migrations against representative old rows and verify no
accepted history/evidence is rewritten. Schema names above are selected directions,
not DDL already applied; final constraints must follow the checkpoint's implementation.

Other interface incompatibilities to resolve in their assigned checkpoint:

1. Detector+Segmenter split and required prompt/BERT/SAM preflight versus a combined,
   prompt-free extractor producing boxes and masks. Replace both cut points together.
2. DetectionBox requires fixture_id and integer boxes; YOLOE needs a provider-neutral
   source/query tag, raw labels/confidence, original-frame float geometry and transform
   provenance. Preserve old JSON readability; do not persist third-party Results/tensors.
3. SQL mask/embedding refs are nullable, but in-memory/runtime zip rules are not. R1/R2
   must make missing masks and legitimate small-region embedding omission explicit,
   retaining uncertainty without fabricating masks/vectors or hiding real failures.
4. The stored debug masked bbox crop differs from DINOv2's padded/letterboxed normalized
   input. R2 should expose enough input/transform metadata (and input preview as needed)
   for exact crop inspection and future point-map alignment.
5. Phase 4 `real` settings currently cannot start without old sources/weights/prompts.
   New extractor settings and config/version hashes must distinguish new runs while
   old snapshots remain historical. Keep provider fake/real explicit; no silent fallback.
6. Revision/physical-object DTOs and old ChangeType names are not the new view-local
   event contract. No cross-camera identity population should become a prerequisite.
7. No current mask-to-point-grid transform/vertex-order/colorization utility exists.
   R5 must test image transforms/validity filtering; a PLY alone is not pixel indexing.

## Precise planned file-by-file checkpoint map

Paths below are relative to `backend/src/scene_tracker/` unless another root is given.
These are future edits, not R0 implementation.

| Checkpoint | Files | Planned action |
|---|---|---|
| R1 | `vision/contracts.py` | Add provider-neutral ObjectExtractor/extraction output; preserve canonical frame/ID contracts and historical serialization. |
| R1 | `vision/detection/yoloe.py` (new) | Local pinned prompt-free YOLOE wrapper; never set_classes; independent result conversion and mask geometry validation. |
| R1 | `vision/detection/fake.py`, `vision/segmentation/fake.py`, `vision/fixtures.py` | Adapt deterministic combined fake extraction with four fixed roles; preserve fixtures/baseline tests. |
| R1 | `core/vision_settings.py`, `core/model_pins.py`, `.env.example` (root) | Extractor selector, YOLOE checkpoint/hash/cache/confidence/imgsz/device; separate DINOv2 asset requirements from legacy BERT/SAM settings. |
| R1 | `vision/readiness.py`, `vision/runtime.py` | Route new readiness/load lifecycle through YOLOE + existing DINOv2; keep legacy real loader disabled/isolated, no old-asset prerequisite. |
| R1 | `application/process.py`, `application/vision_pipeline.py`, `workers/jobs.py` | Snapshot extractor config/provenance, combined extraction→embedding, immutable per-camera outputs, worker-only model loading. Keep current filenames. |
| R1 | `backend/pyproject.toml`, `backend/uv.lock` | Pin/resolve Ultralytics against existing Torch pair after compatibility checks; no weights in tests. Do not upgrade DINOv2/framework without evidence. |
| R1 | `backend/tests/unit/test_real_adapters.py`, `test_model_readiness.py`, `test_fake_pipeline.py`, `test_imports.py`; `backend/tests/integration/test_capture_api.py`, `test_rq_worker.py` | Add stub Results conversion tests, four-camera fake regression, no set_classes, missing-model/no-fallback/API import tests; retain or clearly label legacy adapter tests. |
| R2 | `vision/preprocessing.py`, `vision/masks.py`, `vision/embeddings/dinov2.py`, `application/vision_pipeline.py` | Verify inverse inference transforms/masks at canonical dimensions; edge/tiny/missing regions and optional embeddings; preserve existing DINOv2 crop/model/normalization unless alignment requires a measured change. |
| R2 | `vision/debug/overlays.py`, `vision/debug/report.py`, `api/schemas/captures.py`, `api/routes/captures.py`, `infrastructure/db/repositories.py` | Per-camera extractor/mask/crop metadata and diagnostics; retain current detections/debug API and signed URLs. |
| R2 | `backend/tests/unit/test_yoloe_evidence.py` (new), `backend/tests/integration/test_capture_api.py` | Exact 64×64 pixels/transforms/edges/overlaps/round-trip/persistence tests. |
| R3 | `vision/matching/costs.py`, `vision/matching/intra_view.py`, `application/association.py` (new) | Configurable appearance-led scoring, explicit unmatched option/Hungarian assignment, top-two ambiguity and missing/reappearance lifecycle; no cross-view matches. |
| R3 | `core/tracking_settings.py` (new), `api/schemas/captures.py`, `application/process.py`, `application/vision_pipeline.py` | Snapshot matching weights/thresholds; optional validated reference_capture_id and per-camera chosen baseline metadata. |
| R3 | `domain/contracts.py`, `domain/enums.py`, `infrastructure/db/models.py`, `infrastructure/db/repositories.py`, new migration after 0003 | Track lifecycle/versioned observation/snapshot persistence using additive strategy above. |
| R3 | `backend/tests/unit/test_intra_view.py`, `backend/tests/integration/test_tracking.py` (new) | Stable/moved/label-drift/identical/missing/reappeared, camera isolation, deterministic and versioned-run cases. |
| R4 | `vision/changes/propose.py`, `application/diffs.py`, `application/reviews.py`, `application/revisions.py` (new) | Coarse view events, review decisions, baseline/accepted-state snapshots, atomic idempotent linear revisions/diffs. |
| R4 | `domain/contracts.py`, `domain/enums.py`, `infrastructure/db/models.py`, `infrastructure/db/repositories.py`, additive migration | Extend event vocabularies and track-based accepted state; preserve old object-based rows and constraints. |
| R4 | `api/routes/changes.py`, `api/routes/revisions.py`, `api/schemas/changes.py`, `api/schemas/revisions.py` (new), `api/main.py` | Implement missing planned APIs rather than renaming current capture/process routes; accepted/rejected/proposed distinction and before/after URLs. |
| R4 | `vision/debug/overlays.py`, `vision/debug/report.py`, new unit/service revision/change tests | Camera-local before/after evidence and immutable history checks. |
| R5 | `domain/highlights.py`, `application/highlights.py`, `api/routes/highlights.py`, `api/schemas/highlights.py`, `geometry/point_grid.py` (new), `api/main.py` | Versioned JSON highlight API and pure CPU mask→dense-grid transform/colorization/fake PLY helpers; no PointDiT imports. |
| R5 | new unit highlight/point-grid and API/service tests | Exact pixel/vertex membership, nearest-neighbor transforms, filtering/overlap/order, correct before/after capture/camera/revision. |
| R6 | `vision/detection/grounding_dino.py`, `vision/segmentation/sam2.py`, old branches in `vision/runtime.py`/`readiness.py` | Remove from normal runtime; retain only explicitly archived legacy code/tests if historical provenance needs them. |
| R6 | `core/vision_settings.py`, `core/model_pins.py`, `.env.example`, `backend/pyproject.toml`, `backend/uv.lock` | Remove obsolete prompted/text-encoder/model-specific requirements only after new-path tests pass. Retain any package still used by YOLOE/DINOv2. |
| R6 | `README.md`, `docs/model-setup.md`, `docs/matching-and-diffs.md`, `docs/api.md`, `docs/architecture.md`, `docs/data-model.md`, optional `docs/legacy-vision-pipeline.md`; `AGENTS.md`, original plan status guidance | Replace active setup instructions, preserve historical progress, identify supersession, add exact one-command fake E2E and license/attribution information. Root LICENSE is currently absent; resolve repository licensing deliberately, not by assuming public visibility suffices. |
| R6 | `scripts/smoke-local.sh` or equivalent Python CLI (new), CLI wiring and complete fake E2E tests | Ingest→4-view extraction→track→propose→review/commit→diff→highlight manifest→fake highlighted PLY, with failure/evidence preservation. |

Keep `reconstruction/` unchanged through immediate YOLOE checkpoints unless R5 needs
only a documented JSON boundary; no shared editable ML dependency. Future P9 extends
its currently placeholder worker to dense-point-map-aware real PointDiT, after R0–R6.

## Dependency/model/command baseline

Backend pyproject targets Python 3.11; uv.lock contains 95 packages across all groups.
Vision pins: Torch 2.7.1, TorchVision 0.22.1, Transformers 4.49.0, timm 0.9.16,
Hydra 1.3.2, iopath 0.1.10, addict 2.4.0, yapf 0.43.0, OpenCV-headless 4.11.0.86,
SciPy 1.15.3; NumPy 2.4.6 and pycocotools 2.0.11 are also in the CPU dev selection.
Ultralytics is neither installed nor locked. Torch is not installed in the current
CPU test environment. R0 does not choose a YOLOE package version, install frameworks
or change the DINOv2 selection. Version/checkpoint validation belongs to R1.

`core/model_pins.py` currently pins Grounding DINO
`856dde20aee659246248e20734ef9ba5214f5e44`, SAM 2
`2b90b9f5ceec907a1c18123530e92e794ad901a4`, DINOv2
`7764ea0f912e53c92e82eb78a2a1631e92725fc8`. Keep the chosen DINOv2 ViT-S/14 checkpoint
and source pin initially. Existing real initialization/inference is unvalidated here;
Phase 4 success means tested adapter contracts, not pretrained quality verification.

Existing CLI (from backend/, with the root env file where needed):

```bash
uv run --env-file ../.env --no-group vision scene-tracker worker vision [--burst]
uv run --no-group vision scene-tracker synthetic-capture --output NEW_DIR [--empty] [--moved]
uv run --env-file ../.env --no-group vision scene-tracker model-readiness
uv run --env-file ../.env --group vision scene-tracker model-readiness --runtime
uv run --env-file ../.env --group vision scene-tracker model-smoke --input FOUR_IMAGES --output NEW_DIR
```

These remain legacy extraction commands during R0, not instructions proving YOLOE is
ready. Readiness still requires local old checkpoints, clean source pins and BERT;
the smoke command uses local JSON/immutable storage without database services.
No real smoke, GPU compilation, YOLOE download or PointDiT download was attempted in R0.

## Executed baseline tests

All commands below ran from their own project directory. `UV_CACHE_DIR=/tmp/scene-tracker-uv`
was set for sandbox cache access; test code and selection were unchanged.

| Directory | Command | Observed result |
|---|---|---|
| backend/ | `uv run pytest -q` | 74 passed, 13 integration tests deselected by existing pytest addopts; 110 upstream deprecation warnings |
| backend/ | `uv run ruff check .` | passed |
| backend/ | `uv run ruff format --check .` | passed, 71 files |
| reconstruction/ | `uv run pytest -q` | 1 passed |
| reconstruction/ | `uv run ruff check .` | passed |
| reconstruction/ | `uv run ruff format --check .` | passed, 4 files |
| backend/ | `uv run pytest -q -m integration` with TEST_* settings below | 13 passed, 74 deselected; 45 upstream deprecation warnings |

Service-backed tests used the already-running healthy PostgreSQL, Silo and Redis
containers. No container was started, stopped or recreated. Existing fixtures use
unique temporary PostgreSQL schemas and S3 buckets, and unique test Redis queues;
migration downgrade/re-upgrade and cleanup apply only inside that test-owned state.
No developer schema migration, reset, global flush or existing-bucket deletion ran.

Reproduce service selection with the local Compose example credentials:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://scene_tracker:local-dev-change-me@localhost:5432/scene_tracker'
export TEST_S3_ENDPOINT='localhost:9000'
export TEST_S3_ACCESS_KEY='scene_tracker'
export TEST_S3_SECRET_KEY='local-dev-change-me'
export TEST_REDIS_URL='redis://localhost:6379/0'
cd backend
uv run pytest -q -m integration
```

Unit/API coverage: input-role/MIME/EXIF/size constraints, immutable storage, fake
four-camera contracts/debug bundles, RLE equality, per-camera fault/retry, CPU imports,
readiness/hash errors, stubbed Grounding DINO/SAM/DINOv2 calls and no fake real-mode fallback.
Service coverage: migrations/constraints, actual upload/retrieval, signed S3 downloads,
concurrent/idempotent scheduling, failure/retry, JSON SpawnWorker execution and durable
status after Redis result deletion. Reconstruction covers its import contract only.
No real YOLOE, real pretrained quality, tracking, accepted revision/diff, highlight or
real reconstruction tests exist yet. No CI workflow is present under `.github/workflows/`.

There were no baseline test/lint/format failures. Warnings are the existing
Starlette TestClient/httpx deprecation and pycocotools NumPy array-copy deprecation;
none were suppressed. R0 does not fix these or change inference to make the audit green.

## R0 gate

The endpoint/contract/storage/migration/test map and precise future file list are now
recorded. Minimal additive schema directions and compatibility gaps are identified.
Only the precedence note and audit/status documents changed. **R0 complete; stop before R1.**

Staging note: the supplied plan has three intentional Markdown hard-break lines with
trailing spaces (lines 3–5), reported by the full staged whitespace check. The plan
was preserved verbatim; R0-authored files pass their scoped whitespace check.

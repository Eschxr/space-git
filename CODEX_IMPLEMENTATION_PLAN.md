# Fixed-Camera Scene Tracker — Codex Implementation Plan

**Status:** Implementation specification, starting from a Git repository containing only a basic `README.md`.  
**Backend:** Python, FastAPI, PostgreSQL, S3-compatible object storage, Redis/RQ, `uv`.  
**Core models:** Grounding DINO → SAM 2.1 → DINOv2.  
**Downstream:** PointDiT → per-view `.ply` artifacts for a future Three.js frontend.  
**Primary product:** Queryable and reviewable *semantic* history of a real environment, with immutable multi-view images as evidence.

> **Instructions to Codex:** Implement this plan sequentially, one phase at a time. Do not skip a test gate or start the next phase unless the current phase is passing. At the end of each phase: run the listed commands, update `docs/implementation-status.md` with completed work and outstanding issues, commit if Git is writable, and stop. Do not write a frontend, camera drivers, camera calibration/registration code, OpenUSD logic, or 3D fusion. Never represent a mock-model test as proof of real model quality. Do not download model weights in ordinary unit tests. Avoid adding speculative infrastructure.

## 0. Product contract and non-goals

### Camera configuration — fixed across every capture

The application **receives exactly four already captured image files** as one logical `Capture`. It does not control or register cameras.

| Canonical ID | Placement | Orientation | Role |
|---|---|---|---|
| `cam_01` | ~1 m above floor, around central pole | Outwards, azimuth ~0° | Side view A |
| `cam_02` | ~1 m above floor, around central pole | Outwards, azimuth ~120° | Side view B |
| `cam_03` | ~1 m above floor, around central pole | Outwards, azimuth ~240° | Side view C |
| `cam_04` | ~2 m above floor, above the others | Downwards | Overhead view |

Azimuths are **design metadata, not measured calibration**. The camera layout is fixed per deployment, but actual fields of view and overlaps are **unknown**; 120° orientation separation does not guarantee overlapping imagery. `cam_04` may help identify objects visible from above and at the edge of a side view, but its drastic viewpoint change makes appearance-only re-identification challenging. No intrinsic/extrinsic calibration, rectification, triangulation, 3D metric displacement, or global 3D positioning is part of the MVP. **Only report displacement in pixels / normalized image coordinates**; never label an uncalibrated displacement as metres.

- Input convention: `cam_01.jpg`, `cam_02.jpg`, `cam_03.jpg`, `cam_04.jpg` (accept PNG/WebP too). The `cam_04` role is fixed and enforced.
- Input submission: one four-file set at a time via multipart API or CLI; all four required, each label unique. Each frame retains its own timestamp if supplied, plus one logical capture timestamp. Assume a near-simultaneous capture; warn if timestamps exceed a configurable skew, but do not implement hardware synchronization.
- Source images are immutable and authoritative. Detections, masks, embeddings, object associations, revisions, debug views, and PLY files are derivatives or interpretations.
- No frontend implementation; supply JSON APIs, presigned asset URLs, and inspection bundles usable by a later Node.js/Three.js client.
- No model fine-tuning; default to publicly distributed pretrained checkpoints, pinned upstream source versions, and operator-provided weight files.
- Unit/integration tests use **synthetic images and fake model adapters**; real-image/model validation is a separate, manual activity after code completion.
- Implement a linear, review-driven revision history; Git-like means immutable revisions, change logs, diffs, and historical states. **Physical environments are not software branches**; branching/merging is out of scope.

### Definition of working end-to-end system

Given valid files for `cam_01` through `cam_04`, the system can ingest them, retain originals, enqueue/run Grounding DINO → SAM 2.1 → DINOv2, persist detections/masks/embeddings, associate observations to persistent identities where justified, produce inspectable change proposals, let an operator accept/reject proposals, create a revision, list/retrieve history and before/after evidence, and enqueue PointDiT to produce and retrieve **one or more per-camera PLY files**. A fused global PLY is **not** promised: PointDiT performs monocular geometry estimation and outputs per-image point clouds, which cannot be reliably aligned without additional geometry work.

### Critical algorithmic rule

**Do not equate similar objects across unrelated views automatically.** First construct stable identities over time **inside each fixed camera**; then offer cross-camera candidates, optionally using `cam_04` as an appearance bridge. Cross-camera links are stored with scores and supporting observations and must be reviewable/reversible. With no calibration and potentially non-overlapping views, two identical chairs in different views may be fundamentally ambiguous. Preserve `unknown`, `unobserved`, and `possible_relocation` rather than inventing confident associations. See [Research and matching rationale](#research-and-matching-rationale).

---

## 1. Overall architecture

```text
Four uploaded images (cam_01..cam_04, one Capture)
          |
          v
FastAPI ingestion -> immutable originals (MinIO/S3) + Capture/Frame rows (PostgreSQL)
          |
          v
RQ job: VisionProcessingRun (GPU process)
          |
          +--> per-view detection (Grounding DINO; text prompt catalogue)
          |         |
          |         +--> box-prompted masks (SAM 2.1)
          |                   |
          |                   +--> masked object crops -> DINOv2 embedding
          |
          +--> per-camera temporal matching (stable view-track IDs)
          |         |
          |         +--> conservative cross-view candidate linking
          |                     |
          |                     +--> physical-object identity registry
          |
          +--> proposed semantic changes + evidence/diagnostics
          |
          v
FastAPI review API -> accepted events -> append-only Revision -> history/diff API
          |
          +--> request reconstruction -> independent PointDiT worker (Python 3.12)
                        |
                        +--> per-camera .ply + depth preview -> immutable artifacts
                        +--> signed download URLs for future Three.js client
```

**Process separation:** one lightweight API process; one vision worker with model weights/GPU; one optional PointDiT worker with its own Python environment/GPU. Redis transports jobs, PostgreSQL records durable job and domain state, and object storage holds large blobs. The API must never load `torch`, SAM, DINO, or PointDiT on import. The worker jobs accept primitive IDs and look up all data server-side, not paths provided by clients.

### Proposed repository (create from scratch; do not import the earlier starter scaffold)

```text
scene-tracker/
├── README.md                          # retain/update initial readme
├── AGENTS.md                          # Codex operating rules / checkpoint gates
├── CODEX_IMPLEMENTATION_PLAN.md      # this file
├── .env.example
├── .gitignore
├── .github/workflows/backend-ci.yml
├── backend/
│   ├── pyproject.toml                 # Python 3.11; uv project
│   ├── uv.lock                        # committed
│   ├── .python-version
│   ├── alembic.ini
│   ├── migrations/
│   ├── src/scene_tracker/
│   │   ├── api/{main.py,dependencies.py,routes/,schemas/}
│   │   ├── core/{settings.py,logging.py,errors.py}
│   │   ├── domain/{entities.py,enums.py,events.py,contracts.py}
│   │   ├── application/{ingest.py,process.py,association.py,diffs.py,reviews.py,revisions.py,reconstruct.py}
│   │   ├── vision/
│   │   │   ├── contracts.py
│   │   │   ├── preprocessing.py
│   │   │   ├── detection/{grounding_dino.py,fake.py}
│   │   │   ├── segmentation/{sam2.py,fake.py}
│   │   │   ├── embeddings/{dinov2.py,fake.py}
│   │   │   ├── matching/{intra_view.py,cross_view.py,costs.py}
│   │   │   ├── changes/{propose.py,validate.py}
│   │   │   └── debug/{overlays.py,report.py}
│   │   ├── infrastructure/
│   │   │   ├── db/{models.py,session.py,repositories.py}
│   │   │   ├── storage/{base.py,s3.py,local.py}
│   │   │   └── queue/{base.py,rq.py,inline.py}
│   │   ├── workers/{vision.py,jobs.py}
│   │   └── cli.py
│   └── tests/{unit/,integration/,api/,fixtures/}
├── reconstruction/
│   ├── pyproject.toml                 # separate uv project; Python 3.12 for PointDiT
│   ├── uv.lock                        # separate lockfile
│   ├── .python-version
│   ├── src/reconstruction_worker/{worker.py,pointdit_adapter.py,contracts.py,artifacts.py}
│   └── tests/{unit/,integration/}
├── infra/
│   ├── compose.yaml                   # postgres, redis, minio (no forced GPU container)
│   └── docker/{api.Dockerfile,vision.Dockerfile,reconstruction.Dockerfile}
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── data-model.md
│   ├── model-setup.md
│   ├── matching-and-diffs.md
│   ├── implementation-status.md
│   └── adr/
├── scripts/{generate-synthetic-captures.py,smoke-local.sh}
└── frontend/                           # future frontend lives here; do not implement
```

Use a **single modular Python package** in `backend/` rather than many premature microservices. Reconstruction is deliberately a **separate `uv` project**, not a member of a shared `uv` workspace: PointDiT's upstream recipe uses Python 3.12 / PyTorch 2.7 / CUDA 12.8 and gated DINOv3, and must not force the API/vision dependency resolver to share that environment. The two services communicate through JSON job contracts, database records, and object-storage references; no shared editable Python dependency required initially. For reconstruction jobs, enqueue an **import-path string** (for example `reconstruction_worker.worker.run_reconstruction`) into a dedicated `reconstruction` RQ queue rather than importing the reconstruction package in FastAPI. Use RQ's JSON serializer with primitive IDs and versioned dictionaries (not pickled Python objects), and ensure only the reconstruction worker resolves that job function. Maintain a durable database status even if Redis drops a result or TTL expires.

### Runtime interfaces and dependency boundaries

- `Detector.detect(rgb_image, prompts, config) -> list[DetectionBox]`.
- `Segmenter.segment(rgb_image, boxes, config) -> list[InstanceMask]` (same order or stable input IDs).
- `Embedder.embed(rgb_image, instance_masks, boxes, config) -> list[Embedding]`.
- `TemporalAssociator.match(camera_id, old_tracks, new_detections, config) -> MatchResult`.
- `CrossViewAssociator.propose(capture, per_view_tracks, config) -> list[CrossViewLinkCandidate]`.
- `ChangeProposer.propose(old_accepted_state, latest_observations) -> list[ChangeProposal]`.
- `ArtifactStore.put/get/presign` with `LocalStore` for tests and `S3Store` for production.
- `JobDispatcher.enqueue_vision/enqueue_reconstruction` with inline fake for tests and RQ implementation in production.
- `ReconstructionAdapter.run(images_by_camera, workdir, model_config) -> list[GeneratedPLY]`; concrete PointDiT adapter **only** in `reconstruction/`.

All domain and API contracts use typed Pydantic (or dataclass) models independent of GPU libraries; adapters convert external outputs into canonical contracts. Validate API payloads and object ownership server-side.

---

## 2. Data model and storage conventions

### Relational tables (initial migration)

| Table | Representative fields | Invariants |
|---|---|---|
| `environments` | `id`, `name`, `created_at` | Distinct observed spaces |
| `captures` | `id`, `environment_id`, `captured_at`, `status`, `source_manifest_hash` | Exactly one set of 4 frames when `ready` |
| `frames` | `id`, `capture_id`, `camera_id`, `storage_key`, `sha256`, `width`, `height`, `captured_at` | Unique `(capture_id,camera_id)`; IDs `cam_01`–`cam_04` |
| `processing_runs` | `id`, `capture_id`, `status`, `model_manifest`, `config_hash`, `started_at`, `completed_at`, `error` | Reprocessing is append-only; never overwrite previous output |
| `detections` | `id`, `run_id`, `frame_id`, `label`, `det_score`, `box_xyxy`, `mask_key`, `mask_score`, `embedding_key`, `debug_crop_key` | Per-frame ID, not an object identity |
| `view_tracks` | `id`, `environment_id`, `camera_id`, `status`, `first_seen_at` | Persistent within one fixed camera |
| `track_observations` | `view_track_id`, `detection_id`, `capture_id`, `match_score`, `match_metadata` | Unique detection assignment within a run |
| `physical_objects` | `id`, `environment_id`, `label`, `created_at`, `status` | Stable logical identity; may have multiple view tracks |
| `object_track_links` | `physical_object_id`, `view_track_id`, `source`, `review_status`, `evidence` | Auditable cross-view identity mapping; prevent contradictory assignments |
| `association_candidates` | `id`, `run_id`, `kind`, `source_id`, `target_id`, `features`, `score`, `decision` | Retain rejected/ambiguous hypotheses |
| `change_proposals` | `id`, `run_id`, `object_id`, `type`, `before_ref`, `after_ref`, `evidence`, `status`, `reason` | `proposed`, `accepted`, `rejected`, `needs_review` |
| `revisions` | `id`, `environment_id`, `parent_id`, `capture_id`, `created_at`, `message` | Immutable, ordered accepted history |
| `revision_changes` | `revision_id`, `proposal_id`, `applied_payload` | Accepted events only; unique association |
| `object_state_snapshots` | `revision_id`, `object_id`, `state_json` | Materialized accepted state; optimize query later |
| `jobs` | `id`, `kind`, `subject_id`, `status`, `idempotency_key`, `error` | DB status is authoritative independent of RQ TTL |
| `reconstructions` | `id`, `capture_id`, `revision_id` nullable, `status`, `model_manifest`, `error` | Can be requested independently of commits |
| `artifacts` | `id`, `kind`, `source_id`, `camera_id` nullable, `storage_key`, `sha256`, `content_type` | Immutable derived output references |

Use PostgreSQL normal columns/constraints/indexes for keys, times, IDs, and statuses; JSONB for match features, model metadata, and event payloads. DINOv2 vectors are stored as immutable float32 blobs with dimension/model metadata (in object storage, referenced by `embedding_key`); no `pgvector` is required for a small MVP. If storing them in SQL, use `bytea` plus explicit dtype/length, not an unversioned JSON vector. Check all associations belong to the same environment. Add indexes on `(environment_id,captured_at)`, `(run_id,frame_id)`, `(camera_id,view_track_id)`, `object_id`, `revision_id`, and proposal status.

### Blob keys and immutability

```text
originals/{environment_id}/{capture_id}/{camera_id}/{sha256}.{ext}
vision/{processing_run_id}/{camera_id}/masks/{detection_id}.json
vision/{processing_run_id}/{camera_id}/embeddings/{detection_id}.f32
vision/{processing_run_id}/debug/{camera_id}/detections.png
vision/{processing_run_id}/debug/{camera_id}/masks.png
vision/{processing_run_id}/debug/{camera_id}/crops/{detection_id}.png
vision/{processing_run_id}/debug/temporal_matches.json
vision/{processing_run_id}/debug/cross_view_candidates.json
vision/{processing_run_id}/debug/change_proposals.json
reconstruction/{reconstruction_id}/{camera_id}/pointcloud.ply
reconstruction/{reconstruction_id}/{camera_id}/depth.png
```

- Store original received bytes and their SHA-256, never resave originals as JPEG. Make normalized RGB copies in memory for inference; respect EXIF orientation and consistently describe all box/mask coordinates in the **orientation-corrected frame coordinate system**. Retain original size/orientation metadata for mapping back if necessary.
- Accept image content by decode/signature as well as extension, reject oversized/corrupt files, and apply explicit upload and pixel-count limits. Verify all four roles before finalizing a capture. If partial uploads fail, mark capture `failed` and retain/clean orphan uploads safely.
- Mask codec: COCO compressed RLE (`size`, `counts`, JSON-safe text) stored as a tiny JSON blob. Round-trip with `pycocotools`; never store four full-frame uncompressed mask arrays per detection.
- Store per-stage, per-camera artifacts for inspection, plus a processing manifest recording prompt catalogue, prompt/detection thresholds, checkpoint identifiers + SHA-256, upstream Git commits, device, image normalization, embedding preprocessing, matching parameters, and run timing.
- Use short-lived presigned GET URLs (or authenticated download proxy) for original images, masks, overlays and PLY. A later frontend must not need raw S3 credentials.
- Never delete evidence that is referenced by a committed revision. Postpone retention policy and garbage collection until after the MVP works.

### API surface (versioned JSON; formalize as OpenAPI)

| Method | Route | Behavior |
|---|---|---|
| `POST` | `/api/v1/environments` | Create environment |
| `POST` | `/api/v1/environments/{id}/captures` | Multipart: exactly `cam_01`, `cam_02`, `cam_03`, `cam_04`; optional timestamp |
| `GET` | `/api/v1/captures/{id}` | Capture metadata, four frames and status |
| `POST` | `/api/v1/captures/{id}/process` | Enqueue idempotent vision processing (body: config preset) |
| `GET` | `/api/v1/processing-runs/{id}` | Status, model/config manifest, counts/errors |
| `GET` | `/api/v1/processing-runs/{id}/detections` | Detections/mask refs, per-camera filtering |
| `GET` | `/api/v1/processing-runs/{id}/debug` | Artifact manifest and signed URLs |
| `GET` | `/api/v1/processing-runs/{id}/associations` | Temporal/cross-view links, candidates, scores |
| `POST` | `/api/v1/association-candidates/{id}/decision` | Accept/reject candidate; audit reason |
| `POST` | `/api/v1/object-links` | Manually link/unlink a view track to an object; keep audit |
| `GET` | `/api/v1/environments/{id}/objects` | Persistent objects and view-track membership |
| `GET` | `/api/v1/processing-runs/{id}/changes` | Proposed changes and supporting evidence |
| `POST` | `/api/v1/change-proposals/{id}/decision` | Accept/reject (and optional correction) |
| `POST` | `/api/v1/environments/{id}/revisions` | Commit selected accepted proposals; idempotent |
| `GET` | `/api/v1/environments/{id}/revisions` | Ordered revision history |
| `GET` | `/api/v1/revisions/{id}` | Revision details and materialized object state |
| `GET` | `/api/v1/revisions/{id}/diff` | Structured before/after differences, image evidence |
| `POST` | `/api/v1/captures/{id}/reconstructions` | Enqueue PointDiT job independently of vision revision |
| `GET` | `/api/v1/reconstructions/{id}` | Status, error and available artifacts |
| `GET` | `/api/v1/reconstructions/{id}/artifacts` | Per-camera PLY and preview URLs |
| `GET` | `/api/v1/artifacts/{id}/download` | Redirect to short-lived signed URL or proxy |
| `GET` | `/health/live`, `/health/ready` | Liveness / dependency readiness |

For the MVP a single local operator is assumed; document that authentication is not included. Do not expose the service publicly until authentication and authorization are added. Use stable error codes for invalid capture, missing role, model unavailable, duplicate processing, missing weights, invalid review action, and artifact not ready. Define pagination for history and detection lists.

---

## 3. Matching and semantic difference algorithm

### Why separate *view tracks* and *physical objects*?

The three outward-looking cameras can have little or no overlap, and the overhead camera sees a radically different object silhouette. A DINOv2 vector is useful but is **not a guaranteed physical-object identifier**. A single physical object may be seen simultaneously by several cameras, or may disappear from one view and later appear in another. Conversely, two visually identical objects may be different physical objects. Represent:

1. A **detection** = one segmented instance in one frame in one model run.
2. A **view track** = a persistent sequence of detections in **one camera** across successive captures.
3. A **physical object** = a higher-level identity that links one or more view tracks, only when justified or reviewed.
4. A **cross-view candidate** = a non-committal hypothesis that two view tracks correspond to the same physical object.

This is more robust than immediately assigning every segmentation to one global ID.

### 3.1 Per-camera temporal matching (implement first)

Use each camera's stable pixel coordinate system. Given accepted/recent `view_track` descriptors and new detections from the **same camera**:

1. Normalize box coordinates by width/height; calculate centroid, area, mask IoU if comparing frames of the same dimensions, and L2-normalized DINOv2 embedding.
2. Construct a cost matrix containing: `(1 - cosine_similarity)` appearance, `(1 - mask_iou)` overlap, normalized centroid distance, relative size change, and label mismatch penalty. Mask IoU is particularly helpful for stationary objects; embeddings should help if an object moved.
3. Apply **hard gates** (e.g., incompatible label, impossible jump configured for the capture interval, missing embedding) and allow unmatched rows/columns using dummy assignments. Do *not* force a match.
4. Solve one-to-one matching using `scipy.optimize.linear_sum_assignment`; only accept confident matches with both an absolute-score requirement and a best-vs-second-best margin. Treat all thresholds as **configurable uncalibrated heuristics**, not universally meaningful confidence probabilities.
5. Keep a short history (e.g., last 3 valid observations) and a robust appearance prototype (e.g., normalized average/medoid) per view track to recover from one missed detection. Do not update prototypes with dubious matches.
6. Unmatched detections become tentative new tracks. Unmatched previous tracks become `unobserved`/`occluded_candidate`, **not** removed. Support multiple consecutive missing captures and reappearance.
7. Detect ambiguous pairs (two similar chairs) and export full cost-matrix rows and alternative candidates for review.

Config starter weights may be documented but **must not be hardcoded as validated**; tests should verify known synthetic cost outcomes and gate behavior rather than assert model-quality thresholds.

### 3.2 Cross-camera matching (implement second, conservatively)

- Run **after** per-camera tracking and use view-track appearance prototypes rather than individual unstable detections.
- Generate candidate pair scores using DINOv2 similarity, semantic label compatibility, relative crop shape/colour, and timing of first/last observations; use `cam_04` as a *potential* link to `cam_01`–`cam_03`, not as a presumed geometric anchor.
- Separate pair policies: side↔side pairs (`01↔02`, `02↔03`, `03↔01`), and overhead↔side pairs (`04↔01/02/03`). Different views produce different similarity distributions; log scores by pair type. **Do not infer object co-location from comparable pixel coordinates across cameras.**
- A `same_capture` candidate is informative only where both views could plausibly see the same object; actual overlap is unknown without calibration. Without that information, use appearance to *rank review candidates*, not to prove equality.
- Default `cross_view_auto_link=false`. On confidence + margin criteria, create a **proposed** identity merge. Require reviewer confirmation (via API). Future deployments may enable high-confidence auto-links after testing.
- Store decision, evidence, operator note, and the mapping before/after any link/unlink; preserve stable identities and a reversible audit log. Reject links that would create a contradictory mapping, and never discard original detections.
- If a tracked object disappears from side camera 1 and a similar object appears in side camera 2, propose `possible_relocation`; **do not assume a verified movement**. Keep both view-track hypotheses independent until reviewed.
- An operator may mark two view tracks as distinct despite strong embedding similarity; this explicit negative association should gate subsequent suggestions.

### 3.3 Semantic change proposals

Compare each new capture's evidence to the **last accepted environment state**, while taking account of accepted track links and prior missing observations:

- `added_candidate`: a new track with no approved prior identity; recommend review and/or repeated observation.
- `moved_2d_candidate`: a confidently matched view track with changed mask centroid/bbox beyond jitter tolerance in the same camera; report `dx_px`, `dy_px`, `dx_norm`, `dy_norm` (no metres).
- `appearance_changed_candidate`: a stable object showing repeatable mask/appearance change after filtering lighting/global exposure shifts; **low-confidence unless corroborated**.
- `unobserved`: prior track not detected; do not commit removal based on one absent segmentation.
- `removed_candidate`: only after consecutive absences **and** positive visibility evidence or explicit review; automatic proof of removal is generally not possible in this MVP.
- `possible_relocation`: disappearance in one view plus appearance in another, plausible identity link, still needs review.
- `unchanged`: object observed without material differences; no revision required.

Store both *proposal evidence* and *decision*. A final revision contains only explicitly accepted changes, references their originating processing run/captures/frames/masks, and records the accepted object-state delta. Keep non-accepted proposals queryable. Reprocessing a capture with new model versions creates a new processing run and hypotheses but **never rewrites old revisions**. Do not interpret a class-label change as a physical object modification without review.

### 3.4 Debuggability and observability (mandatory)

For every real or fake run, save deterministic, camera-specific inspection artifacts:

```text
processing_run_x/debug/
  manifest.json                    # all model repos/checkpoints/config, timings, errors
  cam_01/{detections.json,boxes.png,masks.png,crop_index.json,crops/}
  cam_02/{detections.json,boxes.png,masks.png,crop_index.json,crops/}
  cam_03/{detections.json,boxes.png,masks.png,crop_index.json,crops/}
  cam_04/{detections.json,boxes.png,masks.png,crop_index.json,crops/}
  temporal_matches.json            # chosen/rejected links with term-by-term cost
  cross_view_candidates.json       # ranked alternatives per camera pair and reason
  change_proposals.json            # evidence links, uncertainties and rule triggers
  summary.html                     # static generated report ONLY; no frontend app
```

`summary.html` is a simple static debugging report (four contact-sheet images and links to JSON), generated by backend code and downloadable, not an application frontend. Overlays must include detection IDs, label, score, view-track ID (if assigned), and physical-object ID (if linked). Ensure predictable output ordering and mask colors for easier diffs. Log a correlation ID on API request, job, processing run, and artifact. Debugging output must be generated with synthetic fake adapters in CI and without a GPU.

---

## 4. Model provenance, exact upstream links, and environment handling

### Vision models (required for real inference)

| Adapter | Official code and documentation | Checkpoint / exact entry point | Default |
|---|---|---|---|
| **Grounding DINO** | https://github.com/IDEA-Research/GroundingDINO | Swin-T official: https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth ; config: https://github.com/IDEA-Research/GroundingDINO/blob/main/groundingdino/config/GroundingDINO_SwinT_OGC.py | Swin-T OGC; text phrases as dot-separated labels |
| **SAM 2.1** | https://github.com/facebookresearch/sam2 ; predictor examples: https://github.com/facebookresearch/sam2/blob/main/notebooks/image_predictor_example.ipynb | Small weights: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt ; corresponding config: https://github.com/facebookresearch/sam2/blob/main/sam2/configs/sam2.1/sam2.1_hiera_s.yaml | `sam2.1_hiera_small`; `SAM2ImagePredictor` with Grounding DINO boxes |
| **DINOv2** | https://github.com/facebookresearch/dinov2 ; model docs: https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md | ViT-S/14 weights: https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth ; PyTorch Hub name `dinov2_vits14` | ViT-S/14, normalized appearance embeddings |

Model code/weights are distributed under their respective upstream licenses; verify and document each license, **including checkpoint terms**, before deploying. The cited vision repositories list Apache-2.0 for the standard code/weights; this does not cover unrelated DINOv2 specialty models. `MODEL_CACHE_DIR` is configurable and excluded from Git; never embed weight files in application images, source control, test fixtures, or release archives.

**Implementation specifics:** Load Grounding DINO once per worker, run detection on each oriented RGB image, retain input prompt spans/thresholds, and convert boxes into canonical pixel `xyxy`. Call `SAM2ImagePredictor.set_image()` once per frame and segment all detected boxes; retain segmentation quality scores and COCO RLE. Build mask-aware RGB crops with consistent padding, a neutral masked-out background, correct aspect-preserving resizing, and a documented DINOv2 normalization recipe. L2-normalize embedding vectors before similarity. Avoid relying on a model's raw score as a calibrated probability. CPU mode may be slow but should be supported where upstream permits; real CUDA smoke tests remain optional.

**Repeatability:** Record full resolved checkpoint paths and hashes, exact source commits/tags, preprocessing sizes, prompt catalogue version and confidence thresholds. Prefer fixed Git commit dependencies and verified files; use `uv.lock` to pin installed packages. If a package requires compiling CUDA extensions, document compatible Torch/CUDA toolchain and a fallback installation path instead of silently skipping it. For unit tests, load fake adapters through dependency injection, not monkeypatch imports into GPU libraries.

### PointDiT (required for the final **optional-on-demand** PLY path)

- Code / setup: https://github.com/google-research/pointdit
- Model zoo and **exact filenames**: https://github.com/google-research/pointdit/blob/main/MODELS.md
- Official demo recipe: https://github.com/google-research/pointdit/blob/main/scripts/demo_l_512.sh
- Public PointDiT checkpoint repository: https://huggingface.co/haofeixu/pointdit
- Default suggested checkpoint: `pointditl-512-mixdata-nodinov3-240c1a4f.pth` (model zoo), adjusted if hardware requires another model.
- **Required separately gated encoder:** DINOv3: https://github.com/facebookresearch/dinov3 ; required DINOv3 ViT-L/16 weight filename from PointDiT MODEL ZOO: `dinov3_vitl16_pretrain_lvd1689m-8aa4cbdd.pth`. Request access legitimately; never bundle, mirror, bypass, or fabricate this checkpoint.

Upstream PointDiT uses Python 3.12, PyTorch 2.7.0 and CUDA 12.8 in its published setup. `scripts/demo_l_512.sh` accepts arbitrary `.jpg`/`.png` input files and writes `*_pointcloud.ply` plus depth previews. **It performs monocular estimation per image, not calibrated multi-view fusion.** Create a separate reconstruction `uv` environment/worker, stage the four immutable original images with canonical names, invoke the pinned upstream inference entry point via a safe subprocess argument list (`shell=False`), enumerate/verify the four named PLY outputs and previews, and upload them to artifact storage. Record the upstream output structure and execution command version; fail on absent or invalid PLY. The downstream frontend can later load the chosen PLY with Three.js; no frontend or global scene registration is implemented here.

**Availability behavior:** If PointDiT or gated DINOv3 weights are not installed, return a precise `model_unavailable` state/HTTP error with setup instructions. Unit tests still complete with a `FakeReconstructionAdapter` that creates small, valid ASCII PLY fixtures. A fake PLY passing a test does **not** prove real PointDiT execution. Only advertise the real adapter as ready if its executable and both required checkpoints are present and validated.

### `uv` and services

- `backend/` is a standalone `uv` project targeting Python 3.11, using a src layout. Keep API/base dependencies small (`fastapi`, `uvicorn`, `pydantic-settings`, `sqlalchemy`, `psycopg`, `alembic`, `minio`, `redis`, `rq`, `python-multipart`). Add `pytest`, `pytest-asyncio` if necessary, `httpx`, and `ruff` to the `dev` dependency group. Add ML requirements (`torch`, `torchvision`, `numpy`, `scipy`, `opencv-python-headless`, `pillow`, `pycocotools`, official model source packages) to a separate `vision` dependency group with a compatible Torch/CUDA source defined as appropriate for the machine.
- `uv` resolves all groups in one project together; if the model packages cannot coexist cleanly, split `vision/` into a **separate Python project** without changing domain contracts. Never break a working API lock just to match GPU packages. Do not create a root `uv` workspace tying PointDiT to backend dependencies.
- `reconstruction/` is a standalone `uv` project targeting Python 3.12. Pin and document a reproducible PointDiT source commit; use `uv` for its environment while satisfying any upstream build or CUDA requirements. PointDiT must not be an import-time requirement of `backend/`.
- `uv.lock` files must be committed. Local `uv` install: https://docs.astral.sh/uv/getting-started/installation/ ; projects: https://docs.astral.sh/uv/concepts/projects/ ; dependency groups: https://docs.astral.sh/uv/concepts/projects/dependencies/ . Configure optional ML dependencies so `uv sync --no-group vision` works on CPU CI. Never put credentials in lockfiles or source code.

---

## 5. Phase-by-phase implementation (stop/checkpoint after each phase)

Each phase has a **scope**, **outputs**, **automated tests**, and a **stop gate**. Use meaningful Git commits, but do not assume Codex has permission to commit; if not, write the suggested commit message in `docs/implementation-status.md`. Tests requiring Docker should be marked `integration`, not silently skipped in CI; the standard CI path must use fake models and not download weights.

### Phase 0 — Initialize repository and developer experience

**Implement**

- Start from the provided README; create file tree, `AGENTS.md` with phase gating and no-frontend/no-camera-calibration rules, `.gitignore`, `.env.example`, root docs, two independent `uv` projects, Ruff/pytest configuration and CLI entry points.
- `backend/` package with importable `scene_tracker`, FastAPI `/health/live`, basic config loader and structured logging; `reconstruction/` package with importable worker contracts but no PointDiT dependency installation requirement during ordinary backend tests.
- `infra/compose.yaml`: PostgreSQL, Redis, MinIO and a safe bootstrap for bucket creation; named volumes, healthchecks, local-only default ports, credentials from `.env`. Do not require CUDA/Docker GPU for developer startup.
- README: prerequisites, commands to start infra, backend sync/tests, API server and worker; document that model weights are separate.

**Automated tests**: package imports, Pydantic config defaults/overrides, FastAPI TestClient live endpoint, Ruff checks; `docker compose config` validates compose file.

**Gate/commit**: `cd backend && uv sync --no-group vision && uv run --no-group vision ruff check . && uv run --no-group vision pytest` passes; `docker compose -f infra/compose.yaml config` passes. **Stop.** Suggested commit: `chore: initialize python backend and infrastructure`.

### Phase 1 — Domain schemas, storage, database and migrations

**Implement**

- Typed domain enums/contracts for camera roles, captures, frames, detection, mask, embedding metadata, tracks, objects, changes, revisions, jobs and artifacts. SQLAlchemy models and Alembic migration for the tables in §2.
- `ArtifactStore` interface with local filesystem test adapter and MinIO/S3 adapter; immutable write semantics, SHA-256, content-type checking, signed URLs (MinIO SDK). Environment isolation.
- Ingestion helper for one complete four-image set (strict filenames/roles, MIME, checksum, size, timestamps and EXIF orientation; no camera calibration).

**Automated tests**: migration upgrade/downgrade, required/unique four roles, rejecting duplicate/missing/corrupt images and oversized payloads, immutable storage, checksum integrity, EXIF orientation consistency, S3 local emulation with MinIO test service.

**Gate/commit**: unit tests pass offline; Postgres+MinIO integration tests pass under compose. **Stop.** `feat: add immutable capture storage and domain schema`.

### Phase 2 — Capture API and asynchronous job skeleton

**Implement**

- Environment creation and capture upload/list/get API; persisted capture state machine `uploading -> ready | failed`.
- Redis RQ job scheduling and PostgreSQL `jobs` table with idempotency key `(kind,subject,config_hash)`; `InlineDispatcher` for tests. Vision job states `queued,running,succeeded,failed` with progress, failures and clean retries.
- Use **RQ SpawnWorker** on POSIX GPU hosts to avoid unsafe CUDA forking; do not preinitialize CUDA in an RQ parent process. Support a separate worker process. Request handlers enqueue only; model inference never runs in FastAPI handlers.

**Automated tests**: FastAPI multipart four-frame ingest; 422 for missing/duplicate camera; successful retrieval; retry after worker exception; idempotent enqueue and exactly-one logical job record; no `torch` imported by API; Redis integration test (no GPU).

**Gate/commit**: API and queue integration tests pass with Docker infrastructure. **Stop.** `feat: add capture API and job orchestration`.

### Phase 3 — Vision contracts, fixture adapters, inspectable processing pipeline

**Implement**

- Canonical `DetectionBox`, `InstanceMask`, `ObjectEmbedding`, `ProcessingManifest`, `PerCameraResult`; explicit `frame_id`, `camera_id`, image dimensions, pixel coordinate convention and trace IDs.
- Deterministic fake adapters: derive fixed boxes/masks/vectors from synthetic fixture scenario metadata, never claim fake values are ML outputs; fake flows all the way through stored outputs.
- Processing orchestrator iterates `cam_01`,`cam_02`,`cam_03`,`cam_04` in stable order, calls adapters, stores per-stage results, handles zero detections and per-camera faults without corrupting previously committed captures.
- Create static debug artifact generator (RGB box overlays, translucent masks, crop sheets, machine-readable manifests, HTML contact sheet). Include `cam_04` prominently as overhead in reports.

**Automated tests**: synthetic image generator produces 4 valid labeled images (not a real-scene test); fake pipeline returns exact contract fields and aligned masks; mask RLE encode/decode equality; debug files and traceability; failure can be retried as a new run without clobbering old run.

**Gate/commit**: local end-to-end fake run yields 4-frame stored `ProcessingRun` plus debug report. **Stop.** `feat: add testable vision pipeline and diagnostics`.

### Phase 4 — Real Grounding DINO, SAM 2.1 and DINOv2 adapters

**Implement**

- Pin official upstream versions and create operator-friendly `docs/model-setup.md` (links in §4) with checkpoint verification, locally configurable paths, CPU/CUDA notes, and an explicit readiness probe.
- Detector: configure text prompts (e.g., `chair . table . computer monitor . box .`) per environment; Grounding DINO produces boxes/class phrases/scores; canonicalize coords; class-aware NMS/deduplication while preserving ambiguous alternatives for debugging. **A closed prompt catalogue cannot guarantee extraction of unknown object types.**
- Segmenter: SAM 2.1 image predictor, one image encoding per frame and box prompts for each detection; validate binary masks/sizes, save RLE and scores. Maintain relationship to the originating detector box.
- Embedder: DINOv2 ViT-S/14 over padded masked object crops. Record preprocessing and embedding dimension; L2-normalize and reject invalid/zero vectors. Optionally store raw crop and mask-aware crop for debugging.
- `VisionSettings` specifies model names, SHA-256 checks, thresholds, CUDA device, and model cache; check readiness before enqueueing a real run. Default `fake` for CI/tests and `real` via explicit opt-in.

**Automated tests**: adapter contract tests using stubbed upstream model calls (tensor shape, normalized boxes, mask-to-RLE, embedding normalization, batch handling, zero results, model-unavailable behavior); no downloads. Optional **manual-only** smoke command `uv run --group vision scene-tracker model-smoke --input ...` verifies a real four-image inference after weights are installed.

**Gate/commit**: all unit tests pass without GPU; optional smoke CLI documented with a clear failure if weights missing; no hidden fake fallback when `provider=real`. **Stop.** `feat: integrate real vision adapters behind stable contracts`.

### Phase 5 — Same-camera object permanence (highest-priority tracking work)

**Implement**

- Camera-local track creation, track history and appearance prototype persistence. Deterministic matching cost matrix (embedding cosine + mask IoU + center displacement + scale + class penalty) with hard gates and an explicit unmatched option.
- Hungarian assignment, confidence/margin screening, track birth, missed observations, reappearance, conflict/review candidates. Use image-space measurements only, with dimension normalization.
- Store all chosen/rejected assignments and term-by-term costs. Export `temporal_matches.json` and explainable decisions.

**Automated tests**: same chair stationary retains view-track ID; moved chair with low IoU but strong appearance retains ID; two identical chairs near each other become ambiguous rather than swapped; missed detection retains track as unobserved; reappearance reconnects when confident; different camera cannot be matched through same-camera routine; matching deterministic under reordered inputs; duplicate assignment impossible.

**Gate/commit**: track lifecycle tests pass; diagnostics show why matches were proposed/rejected. **Stop.** `feat: persist robust per-camera object tracks`.

### Phase 6 — Conservative four-camera identity association

**Implement**

- Explicit camera-role topology table; compare side-to-side and side-to-overhead separately. Rank cross-view hypotheses using label, DINOv2 embeddings, visual distinctiveness, track history, and concurrent observations.
- Store candidates (including alternatives, negative links, and ambiguity). Do not use pixel-space closeness between different cameras; do not assume known overlap. `cam_04` is preferentially evaluated as a candidate bridge, not treated as automatically correct.
- API for reviewing link proposals and manually linking/unlinking view tracks to a physical-object ID; audit changes. Initialize one logical object per unlinked track provisionally; merge only after accepted links. Preserve track identities when object links change.

**Automated tests**: identical chairs visible in disjoint cameras **not** automatically merged; distinct object with strong matching descriptors generates review candidate; top view vs side view yields no automatic certainty; reviewer links two tracks and query yields one physical object with two view tracks; unlink restores independent identity; contradictory/duplicate link rejected; cross-environment link rejected.

**Gate/commit**: every physical object is traceable to its camera-specific detections, and ambiguous cross-camera cases remain reviewable. **Stop.** `feat: add reviewable multi-view identity association`.

### Phase 7 — Semantic change proposals and review

**Implement**

- Compare latest observations against the last accepted revision state (not only the previous uploaded images). Generate `added_candidate`, `moved_2d_candidate`, `appearance_changed_candidate`, `unobserved`, `removed_candidate`, `possible_relocation`, and `unchanged` under §3 rules.
- Keep thresholds/configuration explicit and conservative; use temporal evidence and reviewer decisions. Attach before/after frame IDs, detection IDs, masks, per-camera viewpoint, pixel/normalized displacements, match reasons and uncertainty. Do not report metric movement.
- Review API accepts/rejects and records comments/corrections without mutating original evidence. Detection model reruns create new hypotheses, never rewrite accepted historical events.

**Automated tests**: unchanged scene gives no proposals; detected new box proposes addition; known chair moved in `cam_01` proposes pixel displacement; global brightness shift does not automatically commit an appearance event; missing object produces `unobserved` not auto-removal; overlapping/occluding synthetic mask does not auto-delete; cross-camera new appearance proposes `possible_relocation`; review decisions are idempotent/auditable.

**Gate/commit**: synthetic second capture yields inspectable proposals with correct source links and statuses. **Stop.** `feat: add explainable semantic change proposals`.

### Phase 8 — Immutable revisions, history, and diff APIs

**Implement**

- Commit selected accepted proposals as a revision with one `parent_id`, provenance, optional message, and deterministic new object state. A capture with no accepted changes does not need a revision; create a baseline revision when user first approves a set of observed objects.
- State snapshots for easy queries and a future event-replay path; atomic commit with uniqueness/idempotency checks. Block commits using an unrelated environment or invalid proposal state.
- History API, `GET /revisions/{id}/diff`, per-object history and evidence URLs; revision response contains before/after observations and annotated overlay URLs, sufficient for a future frontend. No image-delta chains.

**Automated tests**: commit baseline; capture second state; accept move/addition; revision 2 references revision 1; history reconstructs both states; declined proposal absent from revision; double commit is idempotent; after model rerun historical revisions unchanged; API response schema snapshots stable.

**Gate/commit**: two synthetic captures round-trip into a correct immutable revision diff. **Stop.** `feat: add accepted revision history and diff API`.

### Phase 9 — PointDiT integration and PLY artifact delivery

**Implement**

- Independent Python 3.12 `reconstruction/` worker with `uv`; PointDiT adapter plus fake. The backend schedules reconstruction via RQ/DB job payload with capture ID, selected camera IDs (default all four), and model preset. Worker fetches original images using server-side storage credentials, stages images, launches pinned official PointDiT inference safely, identifies each resulting `*_pointcloud.ply`, validates PLY header and non-empty vertex set, and uploads each to immutable storage.
- Expose artifact manifests and signed URLs, preserving `camera_id`, capture and model provenance. The user can request a PLY **for any one selected camera** or all four, but do **not** fuse them or claim world-space alignment. Provide depth PNG when PointDiT emits it.
- Handle absent gated DINOv3 weights with actionable `model_unavailable`/`blocked_missing_weights` status. Separate worker environment/lock so PointDiT dependencies do not destabilize the vision API.

**Automated tests**: fake subprocess produces four valid ASCII PLYs; parser accepts valid PLY/rejects missing/invalid/empty PLY; uploads preserve camera mapping; job failure/retry leaves previous artifacts immutable; `GET` signed link/redirect works; missing weights produce explicit error; backend API imports without PointDiT/torch installed. Optional manual-only smoke with real gated checkpoints, not part of CI.

**Gate/commit**: synthetic capture → fake reconstruction job → per-camera downloadable PLY; all tests pass. Real PointDiT integration callable when operator installs official weights. **Stop.** `feat: add isolated PointDiT PLY reconstruction worker`.

### Phase 10 — Documentation, reliability and final mock E2E acceptance

**Implement**

- Flesh out `README.md` and docs: how to use `uv`, docker compose, database migrations, MinIO bucket setup, workers, model download, environment variables, launch commands, API examples, access to debug reports, review/commit workflow, PointDiT access limitation.
- CI workflow: `ruff check`, `ruff format --check`, unit+API tests in CPU/fake mode; optional service-backed integration suite with ephemeral Postgres/Redis/MinIO; separate light reconstruction tests. Never fetch pretrained weights in CI.
- Idempotency for uploads/jobs/reviews, resource limits (max image bytes/pixels, max concurrent jobs), retries with errors exposed in run metadata, model initialization failures, timeouts, safe subprocess invocation. Optional simple cleanup for unreferenced failed uploads only.
- Write `scripts/smoke-local.sh` or a Python CLI that (a) creates two synthetic four-image captures, (b) processes with fake models, (c) shows associations/proposals, (d) accepts a move/add and commits revision, (e) queries diff and debug artifacts, (f) requests fake PLY and downloads it. Script prints IDs and paths/URLs; no frontend.

**Automated tests**: one complete happy-path integration test and negative-path tests for missing camera, invalid mask, ambiguous identity, model unavailable, failed RQ job, missing PLY, and repeat processing. Validate OpenAPI schema for stable endpoints. Optional `uv run pytest -m integration` runs with compose; default fast tests remain offline.

**Gate/commit**: all CI tests pass and local fake E2E completes; docs explicitly separate mock verification from user-run real four-image/manual ML smoke; checkpoint status is `MVP_CODE_COMPLETE` **only** when real adapters and workflows are implemented and testable, not necessarily experimentally validated. **Stop.** `docs: finalize reproducible end-to-end MVP`.

---

## 6. Setup/runbook Codex must make real (document exact commands in README)

From repo root, assuming Docker, Git, a suitable NVIDIA GPU for real ML inference, and `uv` are installed:

```bash
# Bootstrap once (Codex creates these projects in Phase 0):
cd backend
uv python install 3.11
uv sync --no-group vision          # CPU dev, API and unit tests
uv run --no-group vision pytest
cd ..

# Infrastructure and migrations:
docker compose -f infra/compose.yaml up -d
cd backend
uv run --no-group vision alembic upgrade head
uv run --no-group vision uvicorn scene_tracker.api.main:app --reload
```

For real vision worker, follow pinned Torch/CUDA and official model setup instructions first. In a second terminal:

```bash
cd backend
uv sync --group vision
uv run --group vision scene-tracker worker vision
```

For PointDiT, use a **different** environment/terminal (and potentially a different GPU host) with official checkpoint and gated DINOv3 access:

```bash
cd reconstruction
uv python install 3.12
uv sync
uv run reconstruction-worker
```

These last three entry points (`scene-tracker`, `reconstruction-worker`, and CLI smoke utilities) are **to be implemented by Codex**; they are not expected to exist before the relevant phases. Use `.env` based on `.env.example`, including `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `MODEL_CACHE_DIR`, `VISION_PROVIDER=fake|real`, `POINTDIT_CHECKPOINT`, `DINOV3_WEIGHTS_DIR`, `POINTDIT_SOURCE_DIR`, and `PUBLIC_OBJECTSTORE_ENDPOINT` for presigned URLs reachable by future browsers. Do not commit `.env` or checkpoints.

### Example manual REST workflow after implementation

```bash
# Actual syntax documented and maintained in docs/api.md:
# 1) POST /api/v1/environments
# 2) POST /api/v1/environments/{id}/captures
#    -F cam_01=@cam_01.jpg -F cam_02=@cam_02.jpg
#    -F cam_03=@cam_03.jpg -F cam_04=@cam_04.jpg
# 3) POST /api/v1/captures/{id}/process       => processing_run_id
# 4) GET  /api/v1/processing-runs/{id}/debug  => inspect images/masks
# 5) GET  /api/v1/processing-runs/{id}/associations
# 6) POST association decisions, when ambiguous
# 7) GET  /api/v1/processing-runs/{id}/changes
# 8) POST proposal decisions; POST revision commit
# 9) GET  /api/v1/revisions/{revision_id}/diff
# 10) POST /api/v1/captures/{id}/reconstructions
# 11) GET  /api/v1/reconstructions/{id}/artifacts
# 12) Download the selected cam_04 (or other camera) .ply
```

No automated test is required to judge visual/semantic quality on real images. Nevertheless, the project must supply an **operator-run real-model smoke script** that verifies model weight discovery, executes real inference with user-supplied four images, and creates actual per-camera detections/masks/embeddings and (when PointDiT weights are available) PLY assets. Errors must be reported, not hidden by mock fallbacks.

---

## 7. Codex checkpoint and validation policy

For every phase, append a brief status record under `docs/implementation-status.md`:

```markdown
## Phase N — <title> — completed / blocked
- Commit: <hash or suggested message>
- Files changed: ...
- Commands executed: ...
- Tests passed: ...
- Tests not run and reason: ...
- Decisions/known limitations: ...
- Next phase: ...
```

Codex should stop for human review at the boundary, unless explicitly instructed to continue. If blocked by CUDA, gated DINOv3, private network, or an upstream compilation failure: implement the contract and fake tests, record the real adapter as **blocked** with exact reproduction steps, and do not claim real inference works. Tests must remain deterministic without images, GPUs, or external model downloads.

**Global acceptance checklist**

- [ ] Only four camera roles are permitted; `cam_04` always means overhead.
- [ ] No camera registration, calibration, 3D triangulation, or fake metric location.
- [ ] Immutable originals and model/version provenance persist in object storage/DB.
- [ ] Grounding DINO, SAM 2.1, DINOv2 concrete adapters exist and can use official pretrained checkpoints.
- [ ] Fake pipeline produces four debug overlays, stored masks/crops and matching diagnostics.
- [ ] Same-camera track permanence works in deterministic added/moved/missing/reappeared scenarios.
- [ ] Cross-camera ID links are explainable, reversible, and not automatically forced.
- [ ] Missing detections do not automatically become confirmed removals.
- [ ] Accepted semantic changes create immutable revisable history and API diffs.
- [ ] PointDiT is isolated in its own Python/uv environment; gated DINOv3 is handled explicitly.
- [ ] PointDiT output `.ply` is available **per camera** with download URL; no fabricated fused 3D alignment.
- [ ] Frontend is not implemented; backend API supports eventual Node.js/Three.js viewer.
- [ ] CPU/fake CI and integration suite pass; separate manual real-model smoke is documented.

---

## 8. Research and matching rationale

**Fixed view vs cross-view tracking:** With stable cameras, per-view pixel/mask overlap across time is a high-value signal that should be exploited before trying global re-identification. Cross-camera matching across non-overlapping views is fundamentally harder because object appearance changes with viewpoint and light and no geometric correspondence is known. Surveys distinguish within-camera tracking from inter-camera association and emphasize overlap/appearance limitations: [Multi-camera multi-object tracking review (2023)](https://www.sciencedirect.com/science/article/pii/S0925231223006811) and [Human tracking across camera networks (2017)](https://link.springer.com/article/10.1186/s13634-017-0482-z).

**Use DINOv2 for *candidate ranking*, not as identity truth:** An empirical object re-identification study in office environments compares DINO/DINOv2-style features using cropped objects and cosine similarity, but reliable identity still depends on context and the object set: [Object ReID in an office environment (2026)](https://openjournals.uwaterloo.ca/vsl/article/view/7160). Similar chairs or top-vs-side crops can be indistinguishable. That's why the plan preserves track IDs, alternative hypotheses and reviewer-confirmed cross-camera links.

**Four-camera arrangement:** The three side cameras face ~120° apart and are aimed for panoramic *coverage*, not stereo overlap; the fourth overhead view provides complementary coverage and potentially a linking viewpoint, **not** a universal geometric reference. Without calibration, using the same `(x,y)` in two frames to claim physical co-location is incorrect. See [non-overlapping camera appearance / space-time matching research](https://www.sciencedirect.com/science/article/pii/S1077314207000100) for why uncalibrated association needs caution.

**Mask and model evidence:** Grounding DINO supports phrase-guided boxes ([official usage](https://github.com/IDEA-Research/GroundingDINO)); SAM 2.1 supports bounding-box-prompted image masks ([official predictor](https://github.com/facebookresearch/sam2)); DINOv2 supplies general-purpose visual embeddings ([official models](https://github.com/facebookresearch/dinov2)); COCO RLE supports compact instance-mask storage ([pycocotools mask API](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/mask.py)). Each upstream model output needs a canonical adapter and reproducible manifest.

**PointDiT caveat:** The official [PointDiT demo script](https://github.com/google-research/pointdit/blob/main/scripts/demo_l_512.sh) produces per-image `*_pointcloud.ply`, but [PointDiT MODEL ZOO](https://github.com/google-research/pointdit/blob/main/MODELS.md) states the frozen DINOv3 encoder weights are separately gated. It does not supply calibrated alignment of the four camera-centric outputs. This plan intentionally delivers independent per-view PLY files, preserving a future path to fusion without pretending it has been implemented.

---

## 9. Explicit deferred work

Not for this plan: real camera acquisition/synchronization, camera calibration, spatial registration, triangulation, calibrated depth, global point cloud fusion, mesh construction, OpenUSD, frontend/Three.js components, user accounts, authorization for public deployment, live video tracking, training/fine-tuning, hard real-image accuracy thresholds, large-scale ANN search, sophisticated retention/GC, multi-tenant billing, or automated model-quality certification.

**The useful MVP output is not an automatically perfect 3D world model. It is a reproducible, image-backed semantic history with explainable object associations, plus independent 3D PLY artifacts on demand.**

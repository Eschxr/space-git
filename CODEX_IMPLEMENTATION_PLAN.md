# Scene Tracker — active implementation plan

This plan follows **YOLOE prompt-free segmentation + DINOv2**. It incorporates the
completed R0–R6 refactor and reconciles the original phase numbers with that work.
`CODEX_YOLOE_REFACTOR_PLAN.md` controls vision/tracking architecture. The former
prompted detector/segmenter specification is archived in
[docs/legacy-implementation-plan.md](docs/legacy-implementation-plan.md), not used by
the active pipeline. Do not reintroduce its models, text encoders or dependencies.
Historical implementation records are preserved in
[docs/implementation-status.md](docs/implementation-status.md).

## Execution rules

Read AGENTS.md, this plan, the refactor plan and current implementation status before
editing code. Implement only the requested phase, run its gates, append actual results
and limitations to implementation-status, commit if Git is writable, and stop for review.
Reconcile already-completed refactor work before implementing an old phase again.
Never claim fake/stub tests validate pretrained quality. Never download weights in
unit/CI tests. Do not silently substitute fake inference in real mode. Record blockers.

## Product contract

- Exactly four immutable originals per capture: cam_01..cam_03 fixed side views and
  cam_04 fixed overhead. Preserve bytes, SHA-256, timestamps, original dimensions and
  EXIF orientation. Inference uses canonical EXIF-corrected RGB copies.
- No camera drivers/control, calibration, registration, metric movement, frontend,
  OpenUSD or fused 3D. Normalized image-space measurements apply within one camera.
- Detections/masks/labels/embeddings are model interpretations. Preserve ambiguous
  identities and uncertain changes for review; missing from view is not physically removed.
- Identity is environment- and camera-local `view_track_id`. Optional legacy physical
  object links stay compatible and are never assigned automatically. An overhead view
  supplies its own tracks, not world coordinates or an automatic identity bridge.
- Originals, run evidence and accepted revisions remain immutable. Reprocessing creates
  versioned run outputs. Accepted state applies only selected accepted proposals.

## Architecture and current interfaces

Python 3.11 FastAPI, PostgreSQL, PGSTY Silo/S3, Redis/RQ and uv remain in place.
The API imports no Torch/Ultralytics/DINOv2/NumPy/SciPy; model initialization happens
inside each spawned vision job child, once for its four frames. Queue payloads are
versioned JSON primitive IDs; PostgreSQL owns durable status beyond Redis TTL.

```text
Four original images -> immutable ingestion -> queued vision run
  -> YOLOE prompt-free extraction (boxes + canonical masks, no category prompts)
  -> DINOv2 masked/cropped appearance features
  -> camera-local association + immutable track snapshots + retained prototype refs
  -> coarse image-view change proposals + inspection reports
  -> review -> selected accepted events -> immutable revision + diff
  -> per-source-capture/camera highlight manifest
  -> future independent PointDiT worker -> per-view PLY + mapping sidecar
```

- `ObjectExtractor.extract(rgb_image, config)` returns canonical detection/mask DTOs.
  Production: YOLOE, exact `yoloe-11s-seg-pf.pt`; never call `set_classes()`.
  Fake: explicit PNG fixture metadata, no pretrained inference claimed.
- DINOv2 ViT-S/14 retains masked gray-127 crops, configured padding, square
  letterboxing, 224px bicubic input, ImageNet normalization and L2-normalized
  384-dimensional real float32 vectors. Missing/tiny masks have explicit unavailable
  evidence. Never invent a vector. Stored vectors carry model/dimension/SHA-256.
- Runtime pins: Ultralytics 8.4.0, Torch 2.7.1, TorchVision 0.22.1, OpenCV 4.11.0.86;
  exact DINOv2 source commit is in `core/model_pins.py`. Local checkpoints/hash and
  source checks are mandatory in real mode. Resolver success is not runtime validation.
- `TemporalAssociator` is the pure CPU camera-local scoring/assignment implementation
  in `vision/matching/`. Workers persist its decisions through `application/association.py`.
- Masks use compressed COCO RLE in canonical original-pixel coordinates. Derivative
  blobs remain environment- and run-scoped. Vectors are binary float32, not SQL arrays.
- Existing capture/process/detections/debug/change/revision/highlight routes remain
  compatible. Phase 5 adds read-only `/api/v1/view-tracks/{id}` and `/history`.
  [API details](docs/api.md) and [data model](docs/data-model.md) are authoritative for
  actual routes/schema. Do not recreate scaffold or reset existing data.

Reconstruction remains an independent Python **3.12** uv project, not a shared
workspace/dependency. PointDiT and gated DINOv3 assets are future Phase 9. Pixel-to-point
mapping requires the actual dense map, identical recorded crop/flip/resize/pad transform
and one validity/order filter for XYZ/RGB/change labels. Unordered PLY vertex numbers
do not establish pixel correspondence. Emit one cloud per view; no alignment/fusion.

## Progress and phase reconciliation

| Phase | Current scope/status |
|---|---|
| 0 | Repository/uv/CPU boundaries completed |
| 1 | Four-image contracts, immutable storage, initial SQL schema completed; additive migrations through 0005 |
| 2 | Capture API and durable JSON/RQ jobs completed |
| 3 | Fake contracts and inspectable artifacts completed |
| 4 | Real YOLOE + DINOv2 adapters completed by R1–R2/R6; real runtime/quality still unvalidated |
| R0–R6 | Refactor completed; see docs/refactor-status.md |
| 5 | Consolidate camera-local permanence: explicit prototypes, complete cost/margin diagnostics and readable history; completed at this checkpoint |
| 6 | Remaining: discoverable capture/run/review workflow and complete reference policy; original automatic cross-camera engine superseded |
| 7 | Core proposals/review in R4; remaining: append-only review audit and complete decision/evidence semantics |
| 8 | Core commits/snapshots/event diffs in R4; remaining: complete image/provenance responses, accepted track history, state comparison and acceptance gates |
| 9 | Real PointDiT integration deferred; separate future implementation/hardware/access gate |
| 10 | Fake E2E/docs delivered by R6; real operational validation remains separate |

This mapping does not claim all future phases or real pretrained validation are done.
Complete the remaining Phase 6–8 image-history work below using camera-local identities.
Do not reintroduce the superseded automatic cross-camera engine.

## Phase 5 — Complete same-camera object permanence

### Assessment before implementation

R3 already implements camera-local births, missing counts, last-visible evidence,
Hungarian assignment, unmatched options, ambiguity, reappearance and immutable run
snapshots. R4 implements approved references and accepted history. Reuse those paths.
The remaining Phase 5 work is explicit prototype retention, fuller explainability
and direct history inspection. Real pretrained quality is a separate operator gate;
synthetic tracking contracts can be completed without weights.

### Implement

1. Persist each track's appearance prototype as an immutable observation/vector
   **reference** inside its versioned snapshot. Use a documented last-confident
   embedding policy. Keep provenance (source capture/frame/detection/camera, model,
   dimension/hash/key); do not silently average incompatible vectors or fabricate
   missing evidence. Retain the prototype when a detection has no usable embedding
   or a match lacks appearance confidence, and across missed observations. Ambiguous
   births never replace another track's prototype. Read legacy snapshots without
   rewriting them, deriving a reference from their last visible embedding if available.
2. Score compatible appearance cosine, canonical mask IoU (box fallback), normalized
   centre displacement, scale and soft class consistency. Keep configurable hard gates,
   explicit unmatched options and conservative row/column ambiguity screening.
   Scale gets its own configurable weight. Scores/thresholds are heuristic, not
   calibrated probabilities. No cross-camera matching or automatic physical identity.
3. Retain all candidates: selected, gated, below-threshold, conflicting and ambiguous.
   Persist actual score/cost, normalized term contributions, gate/reject reasons,
   both sides' top-two scores/margins, unmatched decisions, weights and baseline
   source kind/run/capture/revision. Approved state may combine several source runs;
   do not describe it as one processed run. Export `temporal_matches.json` and each
   camera's matching JSON. Keep prototype sources traceable in candidate evidence.
4. Provide paginated read-only camera-local history from immutable snapshots, with
   capture/run identity, run status, missing lifecycle and prototype refs. The registry
   remains advisory latest state; history is not implicitly accepted revision history.
   Old JSON snapshots and already accepted revisions remain readable and immutable.
5. Bump the processing configuration version so old successful runs remain intact
   and cannot be reused as if they contained the new tracking behavior. Use existing
   additive JSON state fields; a new relational migration is unnecessary if the
   current tables already represent the data.

### Required automated tests

- Stationary chair retains its view-track ID.
- Substantial movement with zero/low IoU and strong appearance retains ID.
- Two nearby identical chairs stay ambiguous instead of swapping or merging.
- Missing detection preserves unobserved history; convincing reappearance reconnects.
- Missing intermediate mask/embedding cannot erase the saved appearance prototype;
  later movement can use it. Low-confidence/ambiguous matches cannot corrupt it.
- Different camera inputs are rejected; cam_04 has independent tracks.
- Input reordering is deterministic; duplicate detection/track inputs fail; no duplicate
  assignment occurs. Explicit unmatched and score-boundary cases stay explainable.
- Normalized geometry handles changed dimensions. Scale gate and every term cost/reason
  are inspectable, and cost contributions reproduce the recorded cost.
- Stored history/prototype bytes reload, earlier snapshots/revisions remain unchanged,
  and idempotent repeated processing creates no duplicate observations.
- FastAPI still imports without model/array libraries and real mode has no fake fallback.

### Gate and stop

Run backend lint, format and full offline tests, plus the existing isolated
PostgreSQL/Silo/Redis service suite (including fake E2E). No model downloads.
Record exact tests, skipped manual real validation, migration/data/container effects
and Phase 5 assessment in `docs/implementation-status.md`. Update current progress.
Suggested commit: `feat: persist robust per-camera object tracks`.
**Stop after Phase 5. Do not begin Phase 6 or Phase 9.**

## Remaining Phase 6–8 — complete the image-based history system

R4 delivered core mechanics and a two-capture fake gate, not every original Phase 7/8
requirement. The detailed source audit and requirement mapping are in
[docs/phase8-gap-assessment.md](docs/phase8-gap-assessment.md). Preserve existing
commit/snapshot APIs and complete these phases sequentially, only when requested.
No runtime work on these phases was performed by the assessment.

### Phase 6 — Capture/run/review workflow and reference policy

- List all processing attempts for a capture and expose their provenance/reference
  summaries, using existing captures/runs without recreating the ingestion scaffold.
- Make observed/pending-review/approved state discoverable through typed APIs and a
  usable CLI or documented HTTP workflow; a frontend is not part of this scope.
- Define and test initial/unapproved/approved baseline selection, same-capture reruns,
  explicit debug references, backdated captures and concurrent head advancement.
  Preserve stale-baseline rejection, originals and prior revisions.
- Define no-change/no-commit outcomes. Empty-baseline commits are optional; retain
  the current nonempty restriction explicitly unless a separate extension is added.

**Gate:** clients can discover capture processing history and inspect the current
four-view evidence versus approved state; reference edge cases are deterministic.
Run offline/static and isolated service gates, update implementation status and stop.
This phase replaces the old cross-camera identity engine; manual physical links remain optional.

### Phase 7 — Auditable semantic review completion

- Preserve current appeared/moved/appearance/missing/reappeared/uncertain proposals
  and their accepted-reference comparisons. Improve evidence where required by review.
- Store append-only decisions with previous/new status, decision time, reviewer label
  and reason; keep current status queryable and decision retries idempotent.
- Define what accepting uncertain means, repeated missing/reappearance behavior, and
  which state is applied. Never turn camera-local uncertainty into automatic physical facts.
- If reviewer corrections/reassociation are included, persist explicit reviewed records
  rather than editing detections. Do not make optional cross-camera links a prerequisite.

**Gate:** a multi-capture sequence yields correct source-linked proposals and auditable
accepted/rejected/needs-review transitions; originals/committed payloads are immutable.
Run required offline/service tests, update implementation status and stop.

### Phase 8 — Complete immutable image-history APIs

- Keep atomic idempotent parent-linked commits and approved snapshots; add direct,
  typed revision-level source/run/model/config/immutable-artifact provenance.
- Return historical four-camera source images, approved track states and signed
  mask/crop/annotated-overlay evidence. Clearly distinguish latest source images from
  approved state that may retain evidence from older captures after rejection.
- Add accepted per-view-track revision history, separate from observational run history.
- Preserve the existing ancestor event diff and add explicit endpoint-state comparison,
  with deterministic before/after camera-local evidence across nonadjacent revisions.
  Specify identical/reverse/unrelated comparison behavior. Do not silently rename APIs.
- Complete concurrency/rollback/cross-environment/schema-contract and multi-revision
  lifecycle tests. Reprocessing/failures must leave historical revisions unchanged.
  General event replay, branches/merges and image-delta chains are not required.

**Gate:** baseline→unchanged→move/add→partial rejection→missing→reappearance round-trips
through review/commits into correct linear snapshots, accepted track history, event logs
and state comparisons, with complete image evidence. Run static/offline/service gates,
update implementation status and stop. PointDiT is not part of this gate.

## Future work and operator validation

- Real YOLOE/DINOv2 setup and measured smoke:
  [model setup](docs/model-setup.md), [Codex runbook](docs/codex-real-inference-runbook.md).
  Operator images/assets/runtime are required; actual results must be recorded separately.
- Optional manually reviewed physical-object links require a new scoped request. No
  automatic cross-view identity engine is part of the current MVP.
- Phase 9 requires the separate PointDiT worker, gated DINOv3 assets, actual dense-map
  transform/filter integration, source/highlighted per-view PLY artifact delivery and
  independent real hardware validation. Synthetic colorizer tests do not complete it.
- Reliability beyond the MVP (host-loss job reconciliation, access control and retention)
  remains explicit future work; never delete committed evidence as routine cleanup.

## Commands and implementation-status guidance

See README for exact setup/service commands. To avoid changing an already-installed
real runtime during a code-only gate, use the existing synchronized environment with
`uv run --locked --no-sync` (or select `--group vision` consistently for a real session).
For a new CPU-only environment install `uv sync --locked --no-group vision` first.
From the root, typical Phase 5 checks are:

```bash
uv run --project backend --locked --no-sync ruff check backend scripts
uv run --project backend --locked --no-sync ruff format --check backend scripts
uv run --project backend --locked --no-sync pytest -q backend/tests
# With TEST_DATABASE_URL, TEST_S3_* and TEST_REDIS_URL configured:
uv run --project backend --locked --no-sync pytest -q -m integration backend/tests/integration
```

Append completed/blocked status, actual changes, commands, pass counts, unavailable
real-model gates and known limitations. Keep historical Phase 0–4 and R0–R6 records;
[the archived specification](docs/legacy-implementation-plan.md) is historical only.

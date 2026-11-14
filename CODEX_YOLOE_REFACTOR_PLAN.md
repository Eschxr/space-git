# Scene Tracker — YOLOE MVP Refactor and Point-Cloud Highlight Plan

**Audience:** Codex implementing changes in the **existing** Scene Tracker repository.  
**Starting point:** Original implementation plan Phases **0–4 are implemented**; repository source has **not been provided with this handoff**. Inspect the actual code before making assumptions.  
**Goal:** Replace prompted Grounding DINO + SAM 2.1 extraction with **YOLOE prompt-free segmentation**, retain DINOv2, simplify object tracking and semantic diffs, and ensure accepted change records can later be highlighted in **PointDiT per-view PLY** outputs.  
**Status:** Refactor specification, not a claim that the code has already been changed.

> **Codex execution rule:** Work **one checkpoint at a time**. At each checkpoint, run the required tests, note what changed in `docs/implementation-status.md`, and **stop**. Do not silently carry on to the next checkpoint. Do not pull model weights in automated tests. If the real-model smoke test cannot run on the current machine, record why; never substitute fake inference while claiming real inference worked.

## A. Product contract and constraints

- The backend receives **exactly four immutable images** per capture: `cam_01`, `cam_02`, `cam_03` are ~1 m high, outward-facing, around a pole at approximately 120° intervals; `cam_04` is ~2 m high and points downward. They are fixed between captures. There is **no calibration, registration, or 3D fusion** in this scope.
- The user primarily wants to see **which objects appear to have moved, appeared, disappeared from view, or changed appearance**. Approximate image-space differences are sufficient; no metric distances, exact 3D matching, or comprehensive identity tracking required.
- Retain **source images**, **per-image instance masks**, **object boxes**, **model labels**, **DINOv2 embeddings**, **per-camera view tracks**, **change proposals**, and **accepted revisions**. Detection outputs are model interpretations, not facts about the physical world.
- **First-class unit of identity:** `view_track_id` scoped to one environment **and one camera**. A `physical_object_id` shared between different cameras is optional and **never assigned automatically** in this refactor. Identical chairs in different views are not presumed identical; `cam_04` is not a magic world-coordinate map.
- Keep the Python/FastAPI API, PostgreSQL, S3/MinIO, Redis/RQ and `uv` structure established in Phases 0–4. Keep GPU model imports inside the worker; never introduce model imports at API import time. Keep original stored captures and previously accepted revisions immutable.
- PointDiT stays in its independent Python/`uv` reconstruction project, **later** in the original schedule. No frontend. The interface must support a future Three.js viewer consuming per-camera `.ply` and per-object highlight metadata. Do not claim multiple PLYs represent one globally aligned scene.
- Project is an **open-source hackathon**. YOLOE through Ultralytics is distributed under **AGPL-3.0** or commercial licensing. Preserve appropriate attribution, repository licensing notices, and documentation; do not assert that making a repository public automatically resolves every compliance issue. See [Ultralytics licensing](https://www.ultralytics.com/license).

## B. Target pipeline

```text
POST one Capture containing cam_01.jpg, cam_02.jpg, cam_03.jpg, cam_04.jpg
  -> existing ingestion: immutable image blobs + frame/capture rows
  -> existing queue: VisionProcessingRun
       -> YOLOE prompt-free segmentation (one model, no class prompts)
          -> per-camera detections (class label, score, original-pixel bbox, mask)
       -> DINOv2 on each sufficiently large segmented image crop
          -> normalized appearance embedding + stored crop/mask/debug overlay
       -> same-camera association with prior reference capture
          -> stable view_track_id, scored matches, unresolved candidates
       -> coarse change proposals
          -> appeared_in_view | moved_in_view | appearance_changed |
             missing_from_view | reappeared | uncertain
       -> per-camera image diff overlays + PointDiT highlight manifest
  -> existing review/revision APIs (adapt only where needed)
  -> later: PointDiT worker (one independent point map + .ply per camera)
       -> project current/previous segmentation mask onto generated points
       -> return regular and/or highlighted .ply + highlight sidecar metadata
```

**Eliminate from the normal execution path:** prompt catalogues, Grounding DINO detector, SAM 2.1 box segmentation, mandatory cross-camera entity linking, and any rule that requires precise scene geometry. Existing source code can be **archived or feature-disabled** briefly if removing it would risk breaking the existing code, but it must not be required to configure, start, or execute the new MVP path. Once tests pass, remove unused dependencies and outdated documentation.

## C. Verified pretrained models and setup

| Purpose | Required model | Official link | Notes |
|---|---|---|---|
| Object detection **and** instance masks | **YOLOE prompt-free** `yoloe-11s-seg-pf.pt` | [YOLOE docs](https://docs.ultralytics.com/models/yoloe/), [exact checkpoint](https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-11s-seg-pf.pt), [package](https://github.com/ultralytics/ultralytics) | Initial default: use checkpoint with `-seg-pf.pt`, **never call** `set_classes()` for this checkpoint. A newer `yoloe-26s-seg-pf.pt` is an optional benchmark **only after** proving the default works; it requires a compatible Ultralytics version (documentation says >=8.4.0). |
| Object appearance features | **DINOv2** (existing Phase 4 adapter) | [Official code/weights](https://github.com/facebookresearch/dinov2), [DINOv2-Small model page](https://huggingface.co/facebook/dinov2-small) | Reuse the existing working adapter and its exact chosen checkpoint. Do not reinstall/change its framework unnecessarily. |
| Later monocular point cloud | **PointDiT** | [Official repo](https://github.com/google-research/pointdit), [model zoo](https://github.com/google-research/pointdit/blob/main/MODELS.md), [demo](https://github.com/google-research/pointdit/blob/main/scripts/demo_l_512.sh) | **Deferred** to the reconstruction phase; separate environment; requires separately gated DINOv3 weights. Do not attempt PointDiT downloads during this refactor. |

YOLOE prompt-free uses a built-in vocabulary (~4,585 names) and produces boxes and segmentation masks without an external text encoder. It still may miss objects or label the same object differently between captures. Exact match confidence must therefore be based on **appearance and position too**, not just label string equality.

**Dependency instructions for Codex (adapt to actual project):**

```bash
cd backend
# Preserve existing `uv` groups/torch setup. Add to existing vision group if it exists:
uv add --group vision ultralytics
# Then update uv.lock and document version/checkpoint SHA256.
# Only after verifying the new path: remove unused Grounding DINO/SAM dependencies
# with uv remove --group vision <exact-existing-package-name> as appropriate.
uv sync --group vision
uv run ruff check .
uv run pytest -q
```

For real worker inference, a minimal *illustrative* adapter looks like:

```python
from ultralytics import YOLOE

model = YOLOE("yoloe-11s-seg-pf.pt")
result = model.predict(source="/path/to/cam_01.jpg", conf=0.25, imgsz=640, verbose=False)[0]
# Parse result.boxes.xyxy / .conf / .cls, result.names, and result.masks.
# Avoid making the rest of the system depend on Ultralytics result objects.
```

Codex must **pin and verify** the specific package version on the user's available Python/PyTorch/CUDA environment; no untested claim of plug-and-play support. Model weights download on first use may require network access; support an operator-provided local checkpoint path and a configurable model cache. Do not fetch weights at module import or in CI. Use an explicit `real` vs `fake` model mode and fail clearly if `real` is selected but weights cannot be loaded.

## D. Repository changes — adapt, don't recreate

Before editing, inspect the existing implementation and write a small map in `docs/refactor-audit.md` covering API routes, model interfaces, stored detections, masks, embeddings, queue jobs, schema migrations, tests, and Phase 4 commands. Use existing naming if it is coherent. **Do not recreate the original repository scaffold or reset the database.**

Suggested target directories (illustrative; map to the actual codebase):

```text
backend/src/scene_tracker/
  vision/
    contracts.py                   # canonical detection, embedding, mask contracts
    detection/yoloe.py             # NEW: YOLOE prompt-free adapter
    detection/fake.py              # adapt deterministic fake
    embeddings/dinov2.py          # KEEP; crop/mask extraction adjusted if needed
    matching/intra_view.py         # NEW or simplify existing
    matching/costs.py              # deterministic scored candidates
    changes/propose.py             # approximate event rules
    debug/{overlays.py,report.py}  # preserve existing + match/changes reports
  application/
    processing.py                  # orchestrates YOLOE -> DINOv2 -> tracking
    association.py                 # per-view only by default
    diffs.py                       # approximate changes
    revisions.py                   # preserve accepted revision interface
  infrastructure/db/              # additive migrations only
  workers/                         # GPU model lifecycle + async jobs
  api/routes/                      # preserve existing endpoints and add necessary data
  tests/{unit,integration,api}/
reconstruction/                    # unchanged until future PointDiT checkpoint
  src/reconstruction_worker/
    contracts.py                   # FUTURE: consumes mask/highlight manifest
    ...
docs/
  refactor-audit.md
  refactor-status.md
  matching-and-diffs.md
  model-setup.md
```

### D.1 Canonical detector output

Keep the DTO independent of Ultralytics; don't persist tensors or third-party `Results` objects.

```python
@dataclass(frozen=True)
class ObjectDetection:
    detection_id: str
    frame_id: str
    camera_id: str                  # cam_01 .. cam_04
    class_name: str                 # raw label from YOLOE
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]  # ORIGINAL image pixels
    mask_ref: str | None           # original-image oriented binary mask / COCO RLE
    image_width: int
    image_height: int
    embedding_ref: str | None = None
```

Existing `Detection`/`Segmentation` tables need not be replaced if they can represent this. `mask_ref` is strongly recommended even though tracking can fallback to boxes: **masks are the key to coloring PointDiT points later**. Persist masks as COCO compressed RLE or lossless PNG with explicit `(width,height)`, origin, and orientation. Store an optional normalized bounding box for frontend portability.

**Image space invariant:** Maintain one **canonical, EXIF-corrected original orientation** for each frame; if the input is transformed for inference, explicitly map boxes/masks back and record the transform. The stored masks must be in that canonical frame's pixel coordinates. Handle empty mask arrays, overlapping objects, missing masks, and false positive small regions without crashing.

### D.2 Tracking and change record shape

```json
{
  "change_id": "chg_uuid",
  "kind": "moved_in_view",
  "status": "proposed",
  "camera_id": "cam_01",
  "view_track_id": "trk_uuid",
  "before": {
    "capture_id": "cap_001",
    "frame_id": "frm_001",
    "detection_id": "det_001",
    "mask_ref": "masks/det_001.rle"
  },
  "after": {
    "capture_id": "cap_002",
    "frame_id": "frm_005",
    "detection_id": "det_009",
    "mask_ref": "masks/det_009.rle"
  },
  "image_displacement_norm": 0.12,
  "confidence": 0.78,
  "debug_ref": "debug/runs/run_002/cam_01/match_001.json"
}
```

Numbers above are examples, **not calibrated thresholds**. Distinguish `proposed` from `accepted`/`rejected`. Revisions reference **accepted events and evidence**, not reconstructed geometry. If there is no prior approved baseline, the first capture establishes the initial tracks and **does not emit spurious movement events**.

## E. Simplified matching and diff algorithm

### E.1 Within each camera: reference-selection logic

Process each camera independently. Compare the current capture against the **most recent eligible processed reference** for that environment and camera, preferably the latest accepted baseline; allow a specific `reference_capture_id` to be supplied for debugging. Never compare captures from different cameras by normalized pixel positions. Make the chosen baseline visible in run metadata.

**First pass:** use current detection boxes and masks with prior stored track snapshots. Restrict candidate matching to the same camera. Do not assume exact class-name equality: canonicalize obvious strings (case/plural/whitespace), tolerate nearby synonyms only as a *soft penalty*, and retain raw model labels; visually similar but different objects require spatial checks.

Compute an interpretable match score from:

1. DINOv2 cosine similarity of masked/cropped object appearance (**principal** signal where available).
2. IoU of masks (preferred) or boxes, for stationary/near-stationary objects.
3. Normalized centre displacement and bounding-box size ratio; include a **wide movement allowance** so that moved objects aren't always assigned new IDs.
4. Class/category agreement as a weak consistency term, **not** an absolute gate.

Example starting weights: appearance 0.45, position 0.25, IoU 0.20, class 0.10; **illustrative and configurable**, not proven optimal. Apply candidate gating and an explicit unmatched option; Hungarian assignment (`scipy.optimize.linear_sum_assignment`) over valid candidates is sufficient. Save each candidate score and its component terms in a JSON debug artifact. Do **not** adopt Ultralytics `model.track(persist=True)` as the sole source of durable track IDs; those tracker IDs are scoped to an inference sequence and aren't automatically durable across sparse capture sessions.

**Fallback without DINOv2** (only when embedding computation is legitimately missing): class + position + IoU with a higher uncertainty penalty; do not silently pretend the fallback had strong identity evidence.

**Ambiguity:** If the top two candidates are too close or both poor, assign `uncertain` or create a new view track; never silently merge. A formerly missing view track may be reinstated on an explicit high-confidence reappearance; preserve track history. No automatic cross-camera object permanence. The same physical chair moving from `cam_01` to `cam_02` is `missing_from_view` plus `appeared_in_view` until a future optional human link is made.

### E.2 Coarse difference rules

For each camera:

| Situation | Proposed event | Required evidence |
|---|---|---|
| Track matched, centre moved beyond configurable normalized threshold | `moved_in_view` | Before/after boxes + masks, normalized centre delta |
| Track matched, large area/shape or masked appearance difference, no convincing movement | `appearance_changed` | Before/after image crops and geometric/appearance scores |
| Current detection unmatched | `appeared_in_view` | New detection, new view track, current mask |
| Prior track unmatched | `missing_from_view` | Last visible detection; **never claim physically removed** |
| Missing track confidently matched again | `reappeared` | Prior and restored detection refs |
| Multiple plausible matches, low evidence, or occlusion | `uncertain` | Candidate scores and reason codes |

Set initial thresholds in configuration, not constants hidden in functions. Use normalized image coordinates to accommodate differing camera resolutions. Require more than a few pixels movement, and suppress small-area jitter. Optional OpenCV frame differences can produce `unknown_visual_change` diagnostic regions, but are **not required** and must not pollute the default semantic revision log.

**Important:** `appearance_changed` is a visual change hypothesis, not a guarantee of physical object modification; lighting can cause it. `missing_from_view` does not mean removed. A second observation confirming persistence can be required before promoting uncertain changes; for an interactive hackathon demo, allowing review/accept of single-capture changes is fine.

### E.3 Cross-camera behavior (intentionally minimal)

- Each detection belongs to exactly one camera-specific track.
- Side views `cam_01..03` aim for **coverage**, not stereo; overhead `cam_04` sees a different appearance. No automatic identity merging, no 3D positioning, no inferred physical relocation between cameras.
- If existing Phase 4/earlier schema contains `physical_object_id`, keep it **nullable** and do not auto-populate it. Do not build a new many-camera association engine.
- If time permits, expose a **manual link** between view tracks as optional UI/API metadata only; linking must not rewrite previous detections or commit events. Manual linking is not part of the mandatory test gate.

## F. PointDiT highlight contract — design now, implement PLY coloration later

The change event must be enough to highlight the corresponding **image region and, later, points derived from the same image**. This is why mask references are essential even if the matching algorithm uses only boxes.

### F.1 API-facing highlight manifest (implement during this refactor)

Represent selected changes as a per-camera, per-capture manifest:

```json
{
  "schema_version": "1.0",
  "capture_id": "cap_002",
  "camera_id": "cam_01",
  "frame_id": "frm_005",
  "image": {"width": 1920, "height": 1080, "orientation": "canonical"},
  "regions": [
    {
      "change_id": "chg_uuid",
      "view_track_id": "trk_uuid",
      "change_type": "moved_in_view",
      "temporal_role": "after",
      "detection_id": "det_009",
      "mask_ref": "masks/det_009.rle",
      "bbox_xyxy": [640, 300, 860, 660],
      "highlight_rgb": [255, 196, 0]
    }
  ]
}
```

- `GET /api/v1/captures/{capture_id}/highlights?camera_id=cam_01&revision_id=...` (or an equivalent existing endpoint) returns such a manifest, supporting a revision filter and defaulting to all eligible accepted changes if unspecified. Preserve the actual image/capture references; do not return masks for the wrong capture.
- Include **both** `before` and `after` highlight manifests when comparing two captures; a moved object can be highlighted in both per-view clouds, separately. A missing object can only be highlighted in a **previous** capture, not where no current mask exists.
- A manifest can be rendered as a plain 2D overlay immediately; the future PointDiT worker uses the same information. Colors are UI metadata and may be overridden by the eventual frontend.

### F.2 How future PointDiT PLY highlighting should work (future reconstruction checkpoint)

The official PointDiT inference path produces an **image-aligned dense `(H,W,3)` point map** before writing `*_pointcloud.ply`. Its official export can also filter invalid/depth-edge/sky points. **Do not** assume the nth PLY vertex is the nth pixel of the uploaded image: resizing, filtering, and export ordering must be accounted for.

When implementing the reconstruction worker:

1. Fetch the **same original frame** (or explicitly recorded, canonical derivative) used by YOLOE and the selected revision's highlight mask.
2. Obtain PointDiT's predicted dense point map **and image-processing transform**. Prefer integrating at the existing `save_single_point_cloud` boundary or saving an image-indexed point-map sidecar, not trying to reconstruct pixel correspondence from a previously exported unordered PLY.
3. Convert the original-image mask to the point-map grid using the **same resize/crop/pad transform** as the PointDiT input/output (nearest-neighbor for categorical masks). Explicitly track orientation and any dropped pixels. Check mask/grid shape in assertions.
4. For **each valid exported point**, use the corresponding pixel mask to determine highlight membership before filtering/flattening. Preserve the same validity filter for XYZ, RGB, labels and mask. Avoid silent off-by-one/mirrored projection errors.
5. Write either a `highlighted.ply` with vertex RGB changed, or a PLY with an integer per-point `change_label` plus a JSON sidecar. For easiest Three.js rendering, provide the **highlighted vertex colors** and JSON mapping to change IDs; keep the original unmodified PLY too.
6. Store `capture_id`, `camera_id`, `revision_id`, `mask_refs`, `model_sha`, the image/map transform, point count and colorization version with the artifact. Never claim world coordinates or cross-view alignment.

**Highlight semantics suggestion:** `appeared_in_view` green in the current cloud; `moved_in_view` amber in the before and after clouds; `appearance_changed` blue in both; `missing_from_view` red only in the prior cloud. Each highlighted output is camera-local. With overlapping masks, choose a deterministic precedence and include conflicts in sidecar metadata.

**Important limitation:** PointDiT's official `.ply` alone does not guarantee an accessible pixel-to-vertex index. This refactor must implement and test the **manifest and mask alignment utilities**, while the **PointDiT worker integration** is scheduled later. Don't claim a working highlighted PLY until real/fake PointDiT outputs have been round-tripped through the point-map-aware colorizer.

## G. Debugging and data observability (mandatory)

For **every processed camera**, retain or serve on demand:

- Original image and labelled YOLOE overlay with `detection_id`, YOLOE label, score, and `view_track_id` (if assigned).
- Every mask ref in original image dimensions, optionally an isolated crop PNG and the final DINOv2 crop/embedding metadata.
- Matching report: selected reference capture, every considered candidate, score terms and weights, top-two scores, assignment, reject reason, and config version.
- Before/after comparison with colored boxes/masks/arrows **in that camera's coordinate space**, not on a hypothetical fused world map.
- Change manifest and distinction between `proposed`, `accepted`, `rejected`; JSON should be sufficient to build a future frontend and a small generated HTML debugging report should be usable without Node.js.
- Model provenance: exact checkpoint filename/path/hash, Ultralytics version, DINOv2 version/hash, thresholds, image preprocessing settings, capture/run ID and timestamps.

Avoid logging raw images or crops in application logs; reference stored artifacts instead. Preserve old Phase 4 processing outputs as historical records, even if new runs use a different extractor.

## H. Refactor checkpoints for Codex

### R0 — Audit and baseline (STOP)

**Do:** Read `README.md`, `AGENTS.md`, original `CODEX_IMPLEMENTATION_PLAN.md`, backend `pyproject.toml`/`uv.lock`, Phase 4 code, existing migrations, model interfaces, and tests. Record names of all existing endpoints and data contracts in `docs/refactor-audit.md`. Choose the minimal additive schema changes and list any incompatibilities. Do not change inference yet. **Update `AGENTS.md` immediately with a short precedence note:** `CODEX_YOLOE_REFACTOR_PLAN.md` supersedes the original plan for all vision/tracking work after Phase 4; execute R0–R6 before resuming the old PointDiT phase; stop after each checkpoint. Retain all other existing `AGENTS.md` safeguards.

**Tests:** Run existing `uv run pytest -q` and `uv run ruff check .` from the correct directory, record failures without disguising them. If services required, label them as such. Verify a clean Git diff before modifications.

**Gate:** A precise file-by-file change list exists, tests' baseline status documented. **STOP**. Suggested checkpoint: `docs: audit phase 4 for prompt-free refactor`.

### R1 — YOLOE prompt-free extractor (STOP)

**Do:** Implement canonical `ObjectExtractor` adapter wrapping YOLOE. Replace the production Grounding DINO → SAM 2.1 path with YOLOE only; reuse DINOv2. Add config `VISION_EXTRACTOR=yoloe`, `YOLOE_CHECKPOINT=...-seg-pf.pt`, `YOLOE_CONFIDENCE`, `YOLOE_IMGSZ`, `YOLOE_DEVICE`; keep `VISION_EXTRACTOR=fake`. Adapt worker initialization so a single YOLOE instance is loaded per worker lifetime where possible. Avoid prompts and text encoders completely. Maintain existing capture/process APIs and correct `cam_04` handling. Delete unused runtime dependencies only once no paths import them.

**Tests (offline fake/stubs):** a stub Ultralytics `Results` with two boxes/masks converts correctly, labels map via `.names`, no boxes returns empty list, missing mask handled explicitly, all boxes/masks map to original image dimensions, no `set_classes()` call, fake mode works without `ultralytics` installed, FastAPI imports without CUDA or model imports, outputs from all four cameras are retained.

**Optional manual smoke:** with operator-provided checkpoint on suitable hardware, run one image and inspect bounding boxes/instance masks; this smoke is **not** a CI gate.

**Gate:** Full four-image fake capture passes unchanged public API; model adapter exists and is wired; unit tests pass. **STOP**. Suggested commit: `refactor: use YOLOE prompt-free for object extraction`.

### R2 — Clean image masks, embeddings and inspectable inference (STOP)

**Do:** Standardize canonical orientation, mask RLE or lossless mask refs, original-pixel boxes, masked crops for DINOv2, and normalization of returned embedding vectors. Preserve existing storage keys and old records; use an additive Alembic migration only if actually necessary. Generate overlays and one debug JSON artifact per camera.

**Tests:** synthetic 64×64 images with named mask pixels, size/orientation transforms, edge-touching boxes, overlapping masks, empty detection list, embedding normalization, deterministic crop inputs, masking round trip to exact original coordinates, persistence/reload. No neural weights in tests.

**Gate:** A detection/mask survives save/load and can be overlaid in the right location; camera-separated diagnostics exist. **STOP**. Suggested commit: `feat: standardize inspectable YOLOE evidence`.

### R3 — Minimal same-camera tracks (STOP)

**Do:** Implement or simplify intra-view matching. Use candidate scoring + assignment; persist view-track identity per camera, a small matching score/debug report, last-seen capture, and missing count. Avoid cross-view physical-object association. Keep optional manual links compatible with old data, but don't require them. Restore a missing track only with convincing similarity; ambiguous matches remain pending/new rather than forced.

**Tests:** stable chair remains same ID, chair moves substantially within view, two similar chairs don't collapse into one ID, changed class label doesn't automatically split a track, miss/reappear sequence keeps history, cam_01 and cam_02 objects never automatically receive same view-track ID, cam_04 has own tracks, deterministic ties handled, idempotent rerun uses stable persisted outputs or versioned run snapshots.

**Gate:** Synthetic test suite produces stable **per-camera** track IDs and complete scored decision records. **STOP**. Suggested commit: `feat: coarse per-camera object permanence`.

### R4 — Semantic events, revisions and APIs (STOP)

**Do:** Generate rough change proposals from matched/unmatched tracks and masks. Wire through existing (or originally planned) review, commit, and revision APIs without renaming endpoints unnecessarily. Keep accepted history immutable and distinguish image-view events from physical-world facts. Add API response fields containing `camera_id`, `view_track_id`, before/after detection refs and visualization URLs. No forced cross-view merge screen.

**Tests:** first capture baseline has no false moves, second with moved chair + new box yields move/new, missing object remains `missing_from_view`, lighting-only masked noise under tolerance ignored, uncertain scores not forced into physical-change classification, acceptance commits event, rejection doesn't, diff API returns before/after, reprocessing doesn't mutate earlier revisions, repeated commit idempotent.

**Gate:** Fake two-capture sequence produces inspectable proposed changes and accepted revision diff. **STOP**. Suggested commit: `feat: rough per-camera change history`.

### R5 — Highlight contracts and mock point-map colorization (STOP)

**Do:** Implement per-camera highlight-manifest API and a pure-Python `map_mask_to_point_grid`/`colorize_point_grid` utility **independent of PointDiT imports**. The utility takes canonical mask, explicit image→map transform, dense point map, optional invalid-point filter, and returns precisely matched colored XYZ+RGB rows and metadata. Use the same filtering and order for every attribute. If the original reconstruction project exists but is incomplete, implement the utility in a small shared-format module or duplicate the **JSON contract** rather than coupling Python environments through shared ML dependencies. Provide a fake point-map based export/test PLY; this is not a real PointDiT run.

**Tests:** e.g. 4×4 image with a 2×2 mask highlights exactly those corresponding vertices; resize behavior uses nearest-neighbor; flip/crop transforms tested; filtered points don't shift membership; overlapping masks deterministic; no changes → original colors; invalid manifest/dimension mismatch errors; PLY test has expected colored vertices; JSON endpoint returns correct capture and camera.

**Gate:** Mock highlighted point cloud and highlight sidecar are generated from synthetic points/masks with exact pixel↔vertex accounting. **STOP**. Suggested commit: `feat: provide PointDiT-ready highlight metadata`.

### R6 — Clean dependencies, docs and full fake end-to-end (STOP)

**Do:** Remove unused Grounding DINO/SAM runtime imports and dependencies, unused prompted model settings, and obsolete research stages from the main README. Keep a short `docs/legacy-vision-pipeline.md` note if useful. Verify `AGENTS.md` and original implementation plan's implementation-status guidance explicitly identify this refactor as superseding old Phases 4–8 for the vision side; **do not erase past progress records**. Keep PointDiT as the original separately deployable reconstruction worker. Document exact `uv sync`, queue startup, migrations, models, and a one-command fake two-capture smoke. Optionally provide an operator-run real YOLOE+DINOv2 smoke. Ensure no model downloads in CI.

**Tests:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`; service-backed tests per existing setup; fake end-to-end ingest → process 4 views → track → propose → commit → diff → highlight manifest → fake highlighted PLY; process failures preserve originals and existing revisions.

**Gate:** No prompted model needed; API imports without PyTorch; fake full pipeline passes; model install commands and limitations documented. **STOP**. Suggested commit: `docs: finalize simple image-first MVP refactor`.

### Future P9 — Real PointDiT + highlighted `.ply` (not part of immediate refactor)

Preserve the original PointDiT separate `uv` reconstruction worker. Extend it to collect a revision/capture/camera-specific highlight manifest; obtain dense image-indexed points from the official inference pipeline **before** `.ply` export, apply the mask→grid transform and filter, and write a highlighted `.ply` plus source `.ply` and sidecar. Provide `GET` URLs suitable for Three.js. Tests must compare known synthetic dense grids with known masks and verify the actual PointDiT adapter uses the *same* image transform; hardware/weight availability is a separate manual smoke. The official weights require [PointDiT checkpoints](https://huggingface.co/haofeixu/pointdit) **and** separately gated [DINOv3 weights](https://github.com/facebookresearch/dinov3).

If the user explicitly wants **real** highlighted PLYs in the first demo, move **Future P9** immediately after R5 and make it a separate checkpoint. Do not claim this is complete from R5 synthetic results alone.

## I. API compatibility guidance

Do not introduce an entirely new API if the existing routes can be adapted. Preserve the original workflow:

```text
POST /api/v1/environments
POST /api/v1/environments/{id}/captures       # four files cam_01..cam_04
POST /api/v1/captures/{id}/process
GET  /api/v1/processing-runs/{id}/debug
GET  /api/v1/processing-runs/{id}/changes
POST /api/v1/change-proposals/{id}/decision   # adapt to existing actual route
POST /api/v1/revisions                        # adapt to existing actual route
GET  /api/v1/revisions/{id}/diff
GET  /api/v1/captures/{id}/highlights         # add if none equivalent
# existing reconstruction routes preserved for later PointDiT
```

Continue serving image URLs/mask URLs and model provenance. Where an old endpoint requires cross-camera association, make it optional/empty, not a blocking step. If Phase 4 only implemented the vision layer and later routes are not built yet, leave placeholders for the corresponding later phases; do not invent functional response data.

## J. Definition of done

At refactor completion, using fake adapters (CI) or pretrained models (operator/manual), it must be possible to:

- [ ] Upload four images with correct fixed camera roles; source images stay immutable.
- [ ] Run **YOLOE prompt-free** without category prompts; get actual class labels, boxes and masks; run DINOv2 on object crops.
- [ ] Retrieve a debug overlay and JSON report per camera.
- [ ] Process a later four-image capture and find coarse same-camera moved/new/missing/changed objects; uncertain cases remain visible rather than fabricated.
- [ ] Preserve accepted object-change events and a diff of two revisions through the API.
- [ ] Retrieve **per-camera highlight manifests** with mask refs and correct before/after temporal roles.
- [ ] Produce a **synthetic/test** highlighted PLY using the exact mask-to-dense-point-grid colorizer without needing PointDiT installed.
- [ ] Maintain an isolated, fully specified integration path for future **real** PointDiT highlighted PLYs; do not claim real reconstruction complete unless separately implemented and exercised.
- [ ] Keep all offline tests and static checks green; report all skipped GPU/model and service-backed tests.

## K. How to invoke Codex

Place this file at the repository root as `CODEX_YOLOE_REFACTOR_PLAN.md`. Suggested initial instruction:

> Read `AGENTS.md`, `CODEX_IMPLEMENTATION_PLAN.md`, and `CODEX_YOLOE_REFACTOR_PLAN.md`. The **refactor plan supersedes the older vision architecture** for all future work. Inspect the actual codebase and implement **R0 only**. Run available tests, create `docs/refactor-audit.md`, update `docs/implementation-status.md`, and **stop** at the checkpoint. Do not modify existing data or install model weights during R0.

Subsequent instructions:

> Continue with checkpoint **R1** from `CODEX_YOLOE_REFACTOR_PLAN.md` only. Run the listed tests, document any limitations, commit if allowed, and stop.

**Never skip a checkpoint just because its code looks straightforward.** If dependencies or model versions are blocked, implement the contract and tests, record the blocker, and stop; don't silently switch to a different pretrained model.

## L. Upstream references checked for this plan

- [Ultralytics YOLOE: modes, prompt-free checkpoints, inference and tracking](https://docs.ultralytics.com/models/yoloe/)
- [Ultralytics `Results` box/mask API](https://docs.ultralytics.com/reference/engine/results/)
- [Ultralytics segmented-object crop guide](https://docs.ultralytics.com/guides/isolating-segmentation-objects/)
- [YOLOE original research repository / AGPL-3.0](https://github.com/THU-MIG/yoloe)
- [DINOv2 official implementation](https://github.com/facebookresearch/dinov2)
- [PointDiT official demo: per-image PLY and image resizing](https://github.com/google-research/pointdit/blob/main/scripts/demo_l_512.sh)
- [PointDiT `engine.py`: dense point map before PLY export](https://github.com/google-research/pointdit/blob/main/engine.py)
- [PointDiT official setup and gated DINOv3 requirement](https://github.com/google-research/pointdit)

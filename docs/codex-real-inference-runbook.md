# Codex runbook: real YOLOE + DINOv2 inference

This is an executable instruction sheet for a future Codex session, not a record of
successful real inference. Writing it does not install packages, download weights,
change `.env`, migrate databases or start services. Follow it when explicitly invoked.
The current implementation has passed fake/stub and service tests; actual pretrained
runtime compatibility and output quality remain to be established.

## Copy this request to Codex

Replace the input/output paths. Supply a second capture if you want temporal changes.

```text
Read AGENTS.md, CODEX_IMPLEMENTATION_PLAN.md, CODEX_YOLOE_REFACTOR_PLAN.md,
docs/model-setup.md and docs/codex-real-inference-runbook.md.
Execute the real-inference runbook through its final report. R0–R6 are complete;
this is operator setup/validation, not authorization to begin PointDiT P9.

First real capture: /absolute/path/to/capture-a
Second real capture: /absolute/path/to/capture-b (or omit)
New output directory: /absolute/path/to/new-real-validation-output
Device: cpu (or cuda:0 on a configured NVIDIA Linux worker)

You may install the locked vision dependencies, clone the pinned official DINOv2
source and download the two public pretrained checkpoints listed in the runbook.
You may configure the ignored local .env while preserving unrelated settings,
start missing local Compose services without deleting volumes, apply pending
additive migrations, and run the local API and vision worker for validation.
Use a new, clearly named validation environment for uploaded captures.
Continue through routine setup and checks without repeated confirmation.
Preserve originals and existing application data. Do not accept/commit real change
proposals on my behalf; export them for review. Stop only for missing inputs,
access/permission/hardware blockers or an incompatible pinned model/runtime.
Report exact failures; never substitute fake inference or a different model.
```

The invocation authorizes manual/operator model downloads, outside unit tests/CI.
It does not authorize changing hardware drivers, installing system services, paying
for compute, using private mirrors or accepting gated license agreements for the user.
Use normal tool approval handling where the environment requires it.

## Inputs and completion criteria

- Git and uv, Python 3.11, network access for public packages/source/checkpoints,
  sufficient free disk/memory, and a writable ignored model/output location.
- CPU is the supported choice on the current macOS path. CPU inference can be slow;
  do not promise a latency or RAM requirement without measuring. CUDA requires a
  configured NVIDIA Linux host, compatible driver and available device. Current
  settings do not accept `mps`; do not silently select it or change devices.
- A real directory with exactly four JPEG/PNG/WebP image files named
  `cam_01..cam_04` with matching extensions/MIME. cam_04 must be overhead. Do not
  generate synthetic fixtures and call them real validation. Input files stay immutable.
- A second four-image directory from the same fixed cameras is needed to test
  temporal tracks/change proposals. One capture tests real extraction/embeddings.
- PostgreSQL, Redis and PGSTY Silo are needed for the durable API path. They are not
  needed for the standalone four-image model smoke.

Success means real models load, all four cameras finish, evidence and provenance
are saved, and the durable API/worker run succeeds. Empty detections can be a valid
model result but do not demonstrate useful extraction or DINOv2 execution. Report
whether any nonempty eligible crops actually produced 384-dimensional embeddings.
Human inspection of masks/labels/matches is still needed; execution is not accuracy.

## 1. Inspect and preserve the workspace

1. Read the files in the invocation and current runtime/settings/smoke/worker code.
   Run `git status --short`; preserve unrelated work, including `frontend/`.
2. Resolve repository/input/output/model paths to absolute paths. Check input roles,
   signatures, dimensions and readability without modifying images. If an input is
   missing, ask for its path early while continuing independent dependency/asset setup.
   Do not guess a real image directory from unrelated personal files.
3. Record OS, CPU/architecture, Python/uv versions, free disk/memory and requested
   device. For CUDA inspect driver/device availability; do not install drivers.
4. Use `<repo>/models/real-inference/` for checkpoints, source and cache, and
   `<repo>/local-data/real-inference/<unique-run>/` for outputs/logs unless supplied
   otherwise. These root directories are ignored. Verify this with `git check-ignore`.
   Output directories must be new; never overwrite earlier validation evidence.
5. Preserve root `.env`; if absent, create it from `.env.example`. Put any backup
   inside ignored `local-data/`, not an unignored `.env.backup` beside the original.
   Never print credentials or commit `.env`, backups, model assets or input images.

## 2. Install the exact runtime

From `<repo>/backend`:

```bash
uv sync --locked --group vision
uv run --locked --group vision python -c \
 'import importlib.metadata as m, torch; print({p:m.version(p) for p in ("torch","torchvision","ultralytics","opencv-python","numpy","pycocotools")}); print("cuda_available:",torch.cuda.is_available())'
```

The selected pins are Ultralytics 8.4.0, Torch 2.7.1, TorchVision 0.22.1 and
OpenCV 4.11.0.86; backend Python is 3.11. Do not run `uv add`, upgrade models/frameworks
or regenerate the lock just to get past a failure. Save actual versions/device/errors.

**Shared environment rule:** after installing vision, every uv command using the
same `backend/.venv` must select `--group vision`, or use an already-synchronized
interpreter without syncing. `uv run --no-group vision` can uninstall vision packages;
do not run it concurrently with real workers. Installing packages in the API's venv
does not import them into the API process. Keep heavy imports worker-local.

## 3. Acquire public assets and record provenance

Use only these selections; reuse verified existing local assets if present:

| Component | Official source/artifact |
|---|---|
| YOLOE prompt-free | `https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-11s-seg-pf.pt` |
| DINOv2 ViT-S/14 weights | `https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth` |
| DINOv2 source | `https://github.com/facebookresearch/dinov2.git` at `7764ea0f912e53c92e82eb78a2a1631e92725fc8` |

Create `checkpoints/`, `sources/` and `cache/` under the ignored model directory.
Download with explicit HTTP failure handling and bounded retries, e.g.
`curl --fail --location --retry 3 --output NEW_PART_PATH OFFICIAL_URL`.
Use unique partial files, check successful completion/nonzero size, then move into
an absent final checkpoint path. Never overwrite an existing file with a new download.
Inspect HTTP/content errors; do not save an HTML error as a checkpoint. If redirects
fail, retry the official original URL to obtain a fresh redirect, not an expired
signed asset URL. If access remains blocked, record it and stop dependent work.

Clone DINOv2 into a new source directory, fetch the exact commit if needed, and use
`git checkout --detach 7764ea0f912e53c92e82eb78a2a1631e92725fc8`. Verify HEAD and
clean tracked state. Never reset/clean an existing operator checkout; use another
ignored directory if it is unsuitable. The application imports the local pinned
checkout directly; do not install its research/training requirements or use Torch Hub.

Compute SHA-256 on the complete checkpoint bytes. Compare with a publisher-provided
asset digest if available, and record the URL, retrieval time, byte count, hash and
comparison result in an ignored `asset-manifest.json`. A locally computed hash pins
those downloaded bytes; it is not independent proof of publisher authenticity. Do not
invent an upstream digest or claim a comparison occurred when none was published.
Keep the YOLOE filename exactly `yoloe-11s-seg-pf.pt`. Do not call `set_classes()`.
No Grounding DINO, SAM, BERT/text encoder, PointDiT or DINOv3 is needed for this run.

Official references: [YOLOE modes/checkpoints](https://docs.ultralytics.com/models/yoloe/),
[DINOv2 backbone](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/dinov2/hub/backbones.py).
Preserve [third-party notices](../THIRD_PARTY_NOTICES.md); do not silently accept
new gated terms or claim public hosting alone settles license obligations.

## 4. Configure root .env without exposing secrets

Update only these keys, replacing placeholders with actual absolute paths/hashes:

```dotenv
VISION_PROVIDER=real
VISION_EXTRACTOR=yoloe
YOLOE_CHECKPOINT=/absolute/model-dir/checkpoints/yoloe-11s-seg-pf.pt
YOLOE_SHA256=ACTUAL_64_HEX_SHA256
YOLOE_CONFIDENCE=0.25
YOLOE_IMGSZ=640
YOLOE_DEVICE=cpu
VISION_DEVICE=cpu
VISION_DINOV2_SOURCE_DIR=/absolute/model-dir/sources/dinov2
VISION_DINOV2_CHECKPOINT=/absolute/model-dir/checkpoints/dinov2_vits14_pretrain.pth
VISION_DINOV2_SHA256=ACTUAL_64_HEX_SHA256
MODEL_CACHE_DIR=/absolute/model-dir/cache
VISION_CROP_PADDING=0.1
VISION_EMBEDDING_BATCH_SIZE=16
VISION_MIN_MASK_PIXELS=16
```

Use the requested CUDA device in both device keys only after verifying it. Quote
paths containing spaces as dotenv requires. Preserve database/S3/Redis credentials,
existing deployment overrides and unrelated lines; remove duplicate definitions of
edited keys. Check for inherited shell variables overriding `.env`; avoid printing
secret values. API and worker must resolve the same paths and asset hashes.

## 5. Preflight, initialize, then run standalone real inference

From `<repo>/backend`, keep the installed vision group selected:

```bash
uv run --env-file ../.env --locked --group vision scene-tracker model-readiness
uv run --env-file ../.env --locked --group vision scene-tracker model-readiness --runtime
uv run --env-file ../.env --locked --group vision scene-tracker model-smoke \
  --input /absolute/path/to/capture-a --output /absolute/path/to/NEW-standalone-output
```

Capture exit codes and stdout/stderr to ignored logs, without hiding pipeline failures.
File preflight reports `files_verified_runtime_unprobed`; initialization reports
`models_loaded_inference_unvalidated`. Only the third command runs image inference.
Inspect `run.json`, `manifest.json`, `detections.jsonl`, `summary.html` and the ZIP:
provider real, inference flag true, no camera errors, all four roles, canonical mask
sizes, plausible box/mask alignment, eligible crops and normalized 384-value vectors.
Check actual output structure rather than assuming filenames beyond the current code.
No detections/crops means the embedder's real forward path was not demonstrated.

The standalone smoke intentionally has no database tracking/review. A load failure
may occur before the output directory exists; retain its external stderr log. Do not
substitute fake adapters or lower thresholds until a failing run looks successful.
If initialization exposes a pinned upstream compatibility problem, record the full
exception/package/device context and stop. A model/version change needs a separate,
reviewable decision. Small application defects may be fixed within the existing
contracts with targeted tests; do not rewrite pinned upstream source or broaden scope.

## 6. Validate the durable API/worker path

First inspect Compose configuration/status using root `.env` without exposing resolved
secrets. Reuse healthy containers. If needed, from `<repo>`:

```bash
docker compose --env-file .env -f infra/compose.yaml up -d postgres redis silo silo-init
docker compose --env-file .env -f infra/compose.yaml ps -a
```

Wait for PostgreSQL/Redis/Silo health and successful private-bucket bootstrap. Never
use `down -v`, remove volumes, flush queues or reset the database. Report which
containers were started/reused. Then, from `<repo>/backend`:

```bash
uv run --env-file ../.env --locked --group vision alembic current
uv run --env-file ../.env --locked --group vision alembic upgrade head
# Separate supervised processes/terminals:
uv run --env-file ../.env --locked --group vision uvicorn scene_tracker.api.main:app \
  --host 127.0.0.1 --port 8000
uv run --env-file ../.env --locked --group vision scene-tracker worker vision
```

Do not replace an existing API on that port without checking ownership/configuration;
use another loopback port if needed. Track process handles/PIDs and log paths. The
vision queue may contain prior work: inspect it before starting a consumer; if unrelated
jobs would run, pause for an operator decision or prepare isolated validation services.
Do not drain unrelated work or silently claim an old API uses the new `.env`.

Use the real HTTP API (a short Python/httpx driver is appropriate), not InlineDispatcher
or direct pipeline calls, to do the following:

1. Create a new named environment without prompts. Record its UUID.
2. Upload capture A using its original four files; record capture/frame IDs and hashes.
3. POST `/api/v1/captures/{id}/process` with `{"preset":"default"}`. Record job/run IDs.
4. Poll the run until terminal with a generous configurable timeout; emit periodic
   progress rather than a long silent wait. Do not invent a failure/success on timeout.
5. Require succeeded status, real provider/provenance, four successful cameras and
   real extraction execution. Save all pages of detections, changes and debug metadata.
   Download report, ZIP and relevant evidence before signed URLs expire.
6. If supplied, upload/process capture B in the **same environment** after A completes,
   using the same real configuration and fixed camera roles. Inspect tracking references,
   scored candidates, ambiguity and camera-local IDs; export change proposals/overlays.
7. Recheck original hashes and verify no prior revisions/evidence were changed.

Do not require a predetermined chair count or force movement labels; model detections
can be wrong or empty. Export actual evidence and describe shortcomings. If this queue
is otherwise idle, `worker vision --burst` can be run after enqueueing each capture,
then run again after enqueueing the next; a burst worker exits on an empty queue.

### Optional reviewed revisions/highlights

Processing both captures without accepting A compares against eligible processed
state. To validate an **approved** baseline, present A's proposals for review first,
commit only user-selected accepted IDs, then process B. Review is a semantic decision,
not a prerequisite for model inference. Do not auto-approve real proposals to make
an end-to-end demonstration look successful.

After the user supplies review choices, use [API review/commit calls](api.md), save
the revision diff and query highlights for **both source captures**, each camera and
the selected revision. The MVP requires a nonempty accepted-proposal selection for
a revision. Empty/rejected-only changes legitimately produce no commit/highlights.
Highlight manifests are supported; real PointDiT clouds are not part of this run.

## 7. Checks and final handoff

- Run the API import-boundary test with the real environment installed. If application
  code changed, run relevant offline/static checks with `--group vision` retained.
  Never attach downloads to tests/CI. Existing service tests remain fake-model contract
  tests even when real model packages happen to be installed.
- Record model/source hashes, locked/actual versions, device, timings, per-camera
  results, detections/crops/embedding counts, errors, run/capture/environment IDs and
  local report/bundle paths. Redact credentials; signed URLs are temporary access links.
- Distinguish files verified, models initialized, real inference executed, durable
  workflow exercised and human quality reviewed. Record exactly which occurred.
- Append actual results/blockers to `docs/implementation-status.md`; create/update
  `docs/real-inference-validation.md` only with observed evidence. Do not overwrite the
  historical statement that R0–R6 used fake/stub validation. Do not claim model quality
  from this small smoke or from synthetic tests.
- Stop only processes started by this session; leave pre-existing services alone.
  Report any intentionally left-running services, `.env` changes, migrations and
  model/output locations. Preserve new input/output evidence and all existing data.

## What remains outside this automation

PointDiT real reconstruction is **future P9**, not installed integration awaiting
configuration. It needs implementation in the separate Python 3.12 worker, PointDiT
checkpoints and separately gated DINOv3 assets, plus real dense-map transform/filter
validation. Its [official setup](https://github.com/google-research/pointdit) describes
the separate runtime and gated encoder. Do not combine its environment with backend,
start P9, or label synthetic highlighted PLY as pretrained reconstruction here.

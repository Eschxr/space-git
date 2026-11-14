# YOLOE + DINOv2 operator setup

Real inference is implemented but has **not been exercised on this host**. The
optional ML runtime, local checkpoints and pinned DINOv2 checkout are absent.
Offline/stub tests validate contracts, not pretrained quality. Missing assets fail
with `model_unavailable`; real mode never substitutes fake inference. No test or
startup command downloads weights.

## 1. Install the optional worker environment

From `backend/`, using Python 3.11:

```bash
uv sync --locked --group vision
```

The lock pins Ultralytics **8.4.0**, Torch **2.7.1**, TorchVision **0.22.1** and
OpenCV **4.11.0.86**. Existing Torch/DINOv2 preprocessing is retained. These versions
resolve together; upstream runtime/device compatibility remains unvalidated until
the following real smoke succeeds on your hardware. CPU development uses
`uv sync --locked --no-group vision`, which installs no Torch or Ultralytics.
NumPy, pycocotools, Pillow and SciPy are CPU worker dependencies.

macOS: select CPU. NVIDIA Linux: select an available CUDA device and a driver
compatible with the locked Torch wheel's CUDA runtime. No Grounding DINO extension
build, SAM package, BERT, Transformers, Hydra or external text encoder is needed.
DINOv2's backbone uses Torch directly; xFormers is optional and not installed.

## 2. Supply local assets explicitly

Acquire these separately through the official distribution pages, outside source
control. The commands below do not acquire weights:

| Asset | Exact selection | Source |
|---|---|---|
| YOLOE | `yoloe-11s-seg-pf.pt` | [Official release](https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-11s-seg-pf.pt), [YOLOE docs](https://docs.ultralytics.com/models/yoloe/) |
| DINOv2 | `dinov2_vits14_pretrain.pth`, ViT-S/14 | [Official checkpoint](https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth) |
| DINOv2 source | `7764ea0f912e53c92e82eb78a2a1631e92725fc8` | [Official source](https://github.com/facebookresearch/dinov2/tree/7764ea0f912e53c92e82eb78a2a1631e92725fc8) |

Clone the source yourself and detach at that exact commit. Keep the checkout clean
and separate from the application package. The worker verifies its HEAD, tracked
modifications and import location; no `torch.hub` or source installer is called.
DINOv2 is constructed with `pretrained=False` and loads the local state dictionary.
The YOLOE prompt-free checkpoint never uses `set_classes()`; a prompted or newer
checkpoint is not an automatic replacement.

Compute each hash with `shasum -a 256 PATH` (`sha256sum` on Linux), compare with trusted
artifact information when available, and record it below. Hashes enforce the chosen
operator artifacts; this repository does not invent upstream checkpoint checksums.
Use only trusted checkpoints. Add absolute paths and your verified hashes to root `.env`:

```dotenv
VISION_PROVIDER=real
VISION_EXTRACTOR=yoloe
YOLOE_CHECKPOINT=/absolute/path/to/yoloe-11s-seg-pf.pt
YOLOE_SHA256=YOUR_VERIFIED_64_HEX_DIGEST
YOLOE_CONFIDENCE=0.25
YOLOE_IMGSZ=640
YOLOE_DEVICE=cpu
VISION_DEVICE=cpu
VISION_DINOV2_SOURCE_DIR=/absolute/path/to/dinov2
VISION_DINOV2_CHECKPOINT=/absolute/path/to/dinov2_vits14_pretrain.pth
VISION_DINOV2_SHA256=YOUR_VERIFIED_64_HEX_DIGEST
MODEL_CACHE_DIR=/absolute/path/to/model-cache
```

For CUDA select `YOLOE_DEVICE=cuda:0` and `VISION_DEVICE=cuda:0` explicitly. No
fallback to CPU is performed on a device error. Optional crop/batch settings are
`VISION_CROP_PADDING=0.1`, `VISION_EMBEDDING_BATCH_SIZE=16`, `VISION_MIN_MASK_PIXELS=16`.
Environment prompts are legacy metadata and are ignored by this extractor.

## 3. Check files, then load models, then infer

From `backend/`:

```bash
# CPU-only local file hashes and source checks:
uv run --env-file ../.env --locked --no-group vision scene-tracker model-readiness
# Worker-side real initialization; no inference:
uv run --env-file ../.env --locked --group vision scene-tracker model-readiness --runtime
# Real inference on exactly four supplied images, in a NEW output directory:
uv run --env-file ../.env --locked --group vision scene-tracker model-smoke \
  --input /absolute/path/to/four-images --output /absolute/path/to/new-smoke-output
```

Use filenames `cam_01.jpg` through `cam_04.jpg` (PNG/WebP also supported); cam_04 is
always overhead. Inspect each camera's masks/boxes, crop sheet, JSON, report and
errors. `files_verified_runtime_unprobed` proves only local asset checks;
`models_loaded_inference_unvalidated` proves initialization only. Neither certifies
visual quality. Record hardware/package/device details and inspect actual outputs
before claiming real inference is validated. Failure exits unsuccessfully and
preserves available diagnostics; there is no fake fallback.

The standalone smoke writes local immutable originals and extraction evidence without
PostgreSQL/RQ. Tracking, review and accepted history require the API/worker workflow.
YOLOE uses canonical RGB input with retina masks in original pixel dimensions.
DINOv2 retains mask-aware gray-127 backgrounds, configured crop padding, square
letterboxing, 224px bicubic resizing, ImageNet mean/std and normalized 384-dimensional
float32 vectors. Missing/tiny masks produce explicit unavailable embedding evidence.

## 4. Run through the durable API

Start existing PostgreSQL/Silo/Redis, then from `backend/`:

```bash
uv run --env-file ../.env --locked --no-group vision alembic upgrade head
uv run --env-file ../.env --locked --no-group vision uvicorn scene_tracker.api.main:app
# In another terminal:
uv run --env-file ../.env --locked --group vision scene-tracker worker vision
```

Create an environment with `{"name":"room"}`, upload four files, and process with
`{"preset":"default"}`. The API performs CPU-only preflight, snapshots local asset
paths/hashes/settings, and queues IDs; the worker rechecks those exact assets and
loads one YOLOE instance and one DINOv2 instance for the four views in each spawned
job child. Paths must be mounted identically in API/worker environments. API imports
remain free of Torch, Ultralytics, NumPy and SciPy.

[API examples](api.md) cover proposed changes, review, revision commits and highlights.
[Third-party notices](../THIRD_PARTY_NOTICES.md) link YOLOE/Ultralytics AGPL-3.0 or
commercial licensing and DINOv2 Apache-2.0 terms. Public source hosting alone does not
establish license compliance. PointDiT and its gated DINOv3 weights remain independent
Python 3.12 future P9 work, outside this refactor.

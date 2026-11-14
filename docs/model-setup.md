# Real vision model setup (Phase 4)

The real adapters are implemented behind the same canonical contracts as the fake
pipeline. CPU contract tests inject stub upstream calls; they do not load pretrained
weights or validate model quality. Real inference has **not** been run in this workspace:
operator checkpoints, BERT assets, source checkouts and the optional ML runtime are
not installed. `model-readiness` currently exits 2 with `model_unavailable` and the
missing Grounding DINO checkpoint/hash requirement. There is no fake fallback.

## Source pins and runtime

Use clean operator-managed checkouts at these exact commits. The worker verifies
Git HEAD, rejects tracked modifications and verifies imports resolve inside them.
No checkout, dependency installer or weight downloader runs during inference/tests.

| Component | Official source | Commit |
|---|---|---|
| Grounding DINO Swin-T OGC | [IDEA-Research/GroundingDINO](https://github.com/IDEA-Research/GroundingDINO) | `856dde20aee659246248e20734ef9ba5214f5e44` |
| SAM 2.1 small | [facebookresearch/sam2](https://github.com/facebookresearch/sam2) | `2b90b9f5ceec907a1c18123530e92e794ad901a4` |
| DINOv2 ViT-S/14 | [facebookresearch/dinov2](https://github.com/facebookresearch/dinov2) | `7764ea0f912e53c92e82eb78a2a1631e92725fc8` |

Clone these repositories yourself into a directory outside the application source,
then `git checkout --detach COMMIT` in each checkout. Set absolute source paths in
`.env`. Keep checkouts separate from the API package; no root uv workspace is created.
The Python worker adds verified checkout roots to its import path. SAM 2 configuration
files remain in the source tree, so this also avoids package-data installation drift.

From `backend/`, install the locked optional runtime:

```bash
uv sync --group vision
```

The group pins Torch 2.7.1, TorchVision 0.22.1, Transformers 4.49.0, timm 0.9.16,
Hydra 1.3.2, iopath 0.1.10, OpenCV headless 4.11.0.86 and SciPy 1.15.3. The standard
PyPI Linux Torch wheel locks CUDA 12.6 runtime dependencies; macOS uses the platform
wheel and `VISION_DEVICE=cpu`. CPU CI uses `uv sync --no-group vision`, with no Torch
installation. The shared lock resolves both groups, but only selected groups install.
This resolver success is not a claim of tested upstream runtime compatibility.

Grounding DINO CUDA attention requires its compiled `_C` extension. On a Linux NVIDIA
worker, install a compatible CUDA 12.6 toolkit/NVCC and driver, set `CUDA_HOME`, and
build against the installed Torch pair from the same pinned source:

```bash
# Run in backend/ with VISION_GROUNDING_SOURCE_DIR exported as an absolute path:
uv pip install --no-deps --no-build-isolation -e "$VISION_GROUNDING_SOURCE_DIR"
```

The [official build recipe](https://github.com/IDEA-Research/GroundingDINO/blob/856dde20aee659246248e20734ef9ba5214f5e44/setup.py)
chooses CUDA extensions when the toolkit/device are available. Runtime initialization
requires `_C` for a CUDA device and records its hash/device/runtime. If compilation
fails, record the actual error and use explicitly selected CPU mode for an operator
smoke where practical; never silently change device/provider. The official attention
module has a [CPU Torch path](https://github.com/IDEA-Research/GroundingDINO/blob/856dde20aee659246248e20734ef9ba5214f5e44/groundingdino/models/GroundingDINO/ms_deform_attn.py).
CPU inference can be slow. SAM 2 is imported from its pinned checkout; optional
hole/sprinkle postprocessing and dynamic stability postprocessing are explicitly disabled,
so its optional CUDA connected-components extension is not required by this adapter.
No CUDA build or full upstream model loading was attempted on this host.

## Operator-provided assets

Acquire files separately from their official distribution pages. Never include them
in source control, CI fixtures, container images or release archives.

- Grounding DINO: [Swin-T OGC checkpoint](https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth),
  paired with the pinned `groundingdino/config/GroundingDINO_SwinT_OGC.py`.
- SAM 2.1: [small checkpoint](https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt),
  paired with `configs/sam2.1/sam2.1_hiera_s.yaml` in the pinned package.
- DINOv2: [ViT-S/14 checkpoint](https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth),
  loaded into `dinov2_vits14(pretrained=False)` with strict state matching.
- Grounding DINO additionally uses the tokenizer/encoder assets for
  [google-bert/bert-base-uncased](https://huggingface.co/google-bert/bert-base-uncased).
  Supply an offline directory containing `config.json`, `tokenizer_config.json`,
  `vocab.txt` and `model.safetensors` or `pytorch_model.bin`, plus any accompanying
  tokenizer files. No remote model/tokenizer lookup is performed: worker initialization
  forces Hugging Face/Transformers offline modes and configures this local directory.

Compute checkpoint hashes with `shasum -a 256 PATH` (or `sha256sum` on Linux), compare
against trusted distribution information when available, and set the expected hashes
in `.env`. These configured hashes enforce reproducibility; they are operator-supplied,
not fabricated upstream checksum claims. To compute the directory fingerprint used for BERT:

```bash
uv run --no-group vision python -c \
 'import sys; from pathlib import Path; from scene_tracker.vision.readiness import directory_hash; print(directory_hash(Path(sys.argv[1])))' \
 /absolute/path/to/bert-base-uncased
```

Configure `.env` using the keys in `.env.example`:

```dotenv
VISION_PROVIDER=real
VISION_DEVICE=cpu
VISION_GROUNDING_SOURCE_DIR=/absolute/path/to/GroundingDINO
VISION_SAM2_SOURCE_DIR=/absolute/path/to/sam2
VISION_DINOV2_SOURCE_DIR=/absolute/path/to/dinov2
VISION_GROUNDING_CHECKPOINT=/absolute/path/to/groundingdino_swint_ogc.pth
VISION_GROUNDING_SHA256=YOUR_VERIFIED_64_HEX_DIGEST
VISION_SAM2_CHECKPOINT=/absolute/path/to/sam2.1_hiera_small.pt
VISION_SAM2_SHA256=YOUR_VERIFIED_64_HEX_DIGEST
VISION_DINOV2_CHECKPOINT=/absolute/path/to/dinov2_vits14_pretrain.pth
VISION_DINOV2_SHA256=YOUR_VERIFIED_64_HEX_DIGEST
VISION_BERT_DIR=/absolute/path/to/bert-base-uncased
VISION_BERT_SHA256=YOUR_VERIFIED_DIRECTORY_DIGEST
```

For CUDA use `VISION_DEVICE=cuda:0` (or another available device index). Optional
settings include `VISION_BOX_THRESHOLD=0.35`, `VISION_TEXT_THRESHOLD=0.25`,
`VISION_NMS_IOU=0.5`, `VISION_CROP_PADDING=0.1`, `VISION_EMBEDDING_BATCH_SIZE=16`,
and `MODEL_CACHE_DIR`. Default model names are fixed to the listed architectures.
`VISION_PROMPTS` accepts a JSON array of phrases as the deployment default.
`POST /api/v1/environments` also accepts a `prompts` array per environment, which
supersedes that default for real processing. Empty/dotted phrases are rejected;
the model additionally rejects captions exceeding its 256-token limit. A closed
prompt catalogue cannot guarantee detection of unknown object types.

## Readiness and manual inference

```bash
cd backend
# CPU-only asset hashes/source/config/BERT checks; does not import Torch:
uv run --env-file ../.env --no-group vision scene-tracker model-readiness
# Worker-side model load, dependency/device/extension validation; no inference:
uv run --env-file ../.env --group vision scene-tracker model-readiness --runtime
# Manual-only real inference on one four-image directory; output must not exist:
uv run --env-file ../.env --group vision scene-tracker model-smoke \
  --input /absolute/path/to/four-images --output /absolute/path/to/new-smoke-output
```

The API performs asset preflight before enqueueing and snapshots full resolved paths,
hashes, source commits, thresholds, prompt catalogue and model settings into the run
configuration hash. Files must be mounted at those same paths on the worker. The worker
rechecks them against the snapshot and loads each model once for all four frames in
its spawned child process. API imports never load Torch or upstream model packages.
File preflight reports `files_verified_runtime_unprobed`; it cannot prove a remote
worker's GPU/runtime health. Runtime readiness reports `models_loaded_inference_unvalidated`.
Neither means visual quality is validated. Missing/changed assets, bad source pins,
unavailable devices and initialization errors report `model_unavailable` with setup
instructions; queued-worker failures remain durable failed runs with explicit errors.

The standalone smoke uses local immutable storage and JSON persistence rather than
PostgreSQL/RQ. It preserves originals, writes camera-specific masks/vectors/overlays,
`run.json`, `manifest.json`, `summary.html` and `inspection.zip`. Failures preserve
available diagnostics and exit unsuccessfully. The normal API/worker path persists
those outputs in PostgreSQL/Silo and offers signed URLs as in Phase 3.

## Processing/provenance and license scope

Grounding DINO uses the official 800-pixel short-side/1333 maximum resize and ImageNet
RGB normalization. It converts normalized cxcywh outputs into clipped oriented-frame
pixel xyxy boxes. Same-label NMS preserves threshold/suppression decisions and
alternatives in each camera's `detector_candidates.json`. Different labels remain
alternatives; scores are not calibrated probabilities. SAM 2 encodes each nonempty
frame once and segments all boxes with stable input IDs, retaining binary RLE and
quality scores. DINOv2 uses mask-aware gray-127 backgrounds, box padding, aspect-
preserving square letterboxing, 224px bicubic resize, ImageNet RGB mean/std and L2
normalization; invalid/zero vectors fail explicitly. Embeddings have 384 float32
values with model/dimension/byte-order/hash metadata. No associations are inferred.

The pinned [Grounding DINO license](https://github.com/IDEA-Research/GroundingDINO/blob/856dde20aee659246248e20734ef9ba5214f5e44/LICENSE)
is Apache-2.0; its official README distributes the stated checkpoint under that
repository's terms. The [SAM 2 README](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4/README.md)
states its code/checkpoints use Apache-2.0. The standard DINOv2 ViT-S/14
[model card](https://github.com/facebookresearch/dinov2/blob/7764ea0f912e53c92e82eb78a2a1631e92725fc8/MODEL_CARD.md)
and [BERT model card](https://huggingface.co/google-bert/bert-base-uncased) identify
Apache-2.0. Preserve their notices and review the exact artifact terms before deployment;
this does not extend to unrelated specialty DINOv2 models. PointDiT and gated DINOv3
remain separate Phase 9 work, with no dependency changes to reconstruction/.

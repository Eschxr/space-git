# Model setup status

Phase 3 executes deterministic fake adapters only. No pretrained models are installed
or executed, and no model-quality validation has occurred. Ordinary tests require
no GPU, weights or PointDiT dependencies. The vision group contains CPU NumPy and
pycocotools for compressed RLE, binary vectors and fake fixture processing; dev includes
them for offline tests. API imports do not load these processing libraries or GPU code.
Use `uv sync --group vision` for a worker installation. Fixtures come from explicit
PNG metadata and seed hashes, not learned inference. See README for smoke instructions.

Phase 4 will pin official Grounding DINO, SAM 2.1 and DINOv2 adapters/checkpoints and
operator setup. Until then real-provider scheduling fails with `model_unavailable`.
PointDiT remains deferred to Phase 9 in the separate Python 3.12 environment.
Gated DINOv3 access must be obtained legitimately; real-weight blockers must be
reported explicitly, with no silent substitution of fake inference.

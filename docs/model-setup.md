# Model setup status

No models are installed or executed in Phase 0. Ordinary backend tests require no
GPU, pretrained weights or PointDiT dependencies. The vision dependency group is
empty until Phase 4 pins official adapters and operator setup. PointDiT integration
is deferred to Phase 9 in the separate Python 3.12 reconstruction environment.
Gated DINOv3 access must be obtained legitimately. Missing real weights will be an
explicit blocker, never a reason to silently substitute fake inference.

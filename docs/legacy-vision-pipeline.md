# Retired vision pipeline

The original Phase 4 used Grounding DINO Swin-T OGC → SAM 2.1 small → DINOv2.
R1–R6 replaces extraction with YOLOE prompt-free and retains DINOv2. The old
runtime, settings, detector, segmenter and their dependency-only packages were
removed in R6. Their implementation and tests remain available in Git history
(before R6, including Phase 4 commit `bb92e09`). No old source/weights/BERT assets
are required to configure or run the current system.

Historical detections, artifacts, manifests, physical-object snapshots and revisions
remain readable. Old change enum values remain valid; migrations do not rewrite
those rows. Nullable `environments.prompts` is retained for API/data compatibility
but ignored by the prompt-free pipeline. Its existing phrase validation still applies
when a legacy client submits it. Legacy object events without a canonical camera,
track and mask contract are excluded from new point-grid highlight manifests.

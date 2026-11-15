# YOLOE refactor status

`CODEX_YOLOE_REFACTOR_PLAN.md` supersedes older vision/tracking instructions after
Phase 4. Historical phase records remain in [implementation-status.md](implementation-status.md).

| Checkpoint | Status |
|---|---|
| R0 — Audit and baseline | Completed; [audit](refactor-audit.md), 74 backend offline tests, 13 service tests and 1 reconstruction test pass; lint/format pass |
| R1 — YOLOE prompt-free extractor | Completed: offline/stub and service gates pass; real inference unvalidated |
| R2 — Canonical masks/embeddings/inspection | Completed: optional evidence and alignment gates pass |
| R3 — Same-camera tracks | Completed: deterministic camera-local matching and lifecycle gates pass |
| R4 — Events/revisions/APIs | Completed refactor gate: core review, immutable approved states and event diffs pass; full Phase 7/8 completion remains |
| R5 — Highlight manifests/mock colorizer | Completed: temporal manifests and exact dense-grid mock PLY gates pass |
| R6 — Cleanup/docs/full fake E2E | Completed: 82 offline, 18 service and 1 reconstruction tests pass; lint/format pass |
| Phase 5 — Camera-local tracking consolidation | Completed: 87 offline and 19 service tests pass; [assessment](phase5-assessment.md) |
| Phase 6 — Capture/run workflow and references | Completed: discoverable attempts/evidence, frozen queued references and inspection policies |
| Phase 7 — Auditable review | Completed: immutable decision trail, idempotent retries and explicit uncertainty/lifecycle semantics |
| Phase 8 — Complete image history | Completed: provenance/evidence APIs, accepted track history and endpoint comparisons; 90 offline and 26 Linux service tests pass |
| Future P9 — Real PointDiT/highlighted PLY | Deferred; outside this completed refactor |

## Historical R0–R6 and Phase 5 execution record

R0–R6 are complete. The user explicitly authorized all remaining checkpoints in one
run; sequential gates and checkpoint commits were retained. That request stopped
after R6. The subsequent Phase 5 request is now completed and **stopped at Phase 5**.
Future P9 was not started. No new containers were started or model weights downloaded;
existing PostgreSQL, Redis and PGSTY Silo containers remained healthy. The development
database was not migrated/reset; apply additive migrations with the README command.

Real YOLOE/DINOv2 inference is still **unvalidated**: the optional Torch/Ultralytics
runtime, local checkpoints and pinned DINOv2 source are absent. The local readiness
probe exits 2 with `model_unavailable`; optional manual setup is in
[model-setup.md](model-setup.md). Fake/stub tests prove contracts, not pretrained quality.
No PointDiT inference or real reconstructed/highlighted PLY is claimed.

Run `scripts/smoke-fake.sh /absolute/path/to/new-output` with existing local services.
The verified export is `/tmp/scene-tracker-refactor-e2e-passed` (report, ZIP, diff,
manifests and source/highlighted synthetic PLY plus mapping sidecars). Exported test
service data is cleaned and signed URLs expire; local export files remain available.
Current behavior/constraints: [API](api.md), [matching](matching-and-diffs.md),
[highlights](highlights.md), [legacy note](legacy-vision-pipeline.md).


The subsequent Phase 6–8 implementation completes the workflow/reference, review audit,
revision evidence, accepted track history and state comparison gaps identified in
[the assessment](phase8-gap-assessment.md). The older checkpoint and real-model
validation statements above describe their original refactor/Phase 5 run. Current
history implementation gates and local runtime effects are recorded in
[implementation-status](implementation-status.md). Phase 9 remains deferred.

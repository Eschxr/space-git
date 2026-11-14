# YOLOE refactor status

`CODEX_YOLOE_REFACTOR_PLAN.md` supersedes older vision/tracking instructions after
Phase 4. Historical phase records remain in [implementation-status.md](implementation-status.md).

| Checkpoint | Status |
|---|---|
| R0 — Audit and baseline | Completed; [audit](refactor-audit.md), 74 backend offline tests, 13 service tests and 1 reconstruction test pass; lint/format pass |
| R1 — YOLOE prompt-free extractor | Completed: offline/stub and service gates pass; real inference unvalidated |
| R2 — Canonical masks/embeddings/inspection | Not started |
| R3 — Same-camera tracks | Not started |
| R4 — Events/revisions/APIs | Not started |
| R5 — Highlight manifests/mock colorizer | Not started |
| R6 — Cleanup/docs/full fake E2E | Not started |
| Future P9 — Real PointDiT/highlighted PLY | Deferred until after R0–R6 |

R0 does not change inference, install Ultralytics/frameworks/weights, alter schemas,
reset a database or certify real model quality. Stop for review before R1.

# Phase 5 assessment and completion

The repository was suitable for Phase 5: R0–R6 had replaced the prompted architecture
with YOLOE prompt-free extraction + DINOv2, and the initial Phase 5 baseline passed
**82 offline tests**. PostgreSQL, Redis and PGSTY Silo were already healthy. Real-model
assets/runtime remain a separate validation gate; they are not needed for deterministic
tracking contract tests. No retired detector/segmenter was reintroduced.

The phase reuses R3/R4 rather than building duplicate tracking/revision machinery.
The active root implementation plan now describes YOLOE + DINOv2 and phase mapping;
the prior specification is preserved in [the legacy archive](legacy-implementation-plan.md).
Historical completion records remain unchanged in implementation-status.

| Requirement | Existing refactor coverage | Phase 5 completion |
|---|---|---|
| Camera-local identity/lifecycle | R3 births, misses, last-seen, reappearance and snapshot rows | Revalidated four-view isolation/history and duplicate prevention |
| Appearance persistence | Each observation held its own immutable embedding | Explicit last-confident prototype survives a mask/vector gap and remains source-traceable |
| Scoring/assignment | Appearance/position/IoU/class, area gate, Hungarian/unmatched | Scale contribution, reproducible cost components, explicit gate/rejection reasons |
| Ambiguity/diagnostics | Conservative row/column ambiguity and all candidates | Top-two valid scores/margins, eligible counts, unmatched reasons, actual prototype reference |
| History inspection | Run debug artifacts and accepted revision states | Paginated read-only view-track registry/history endpoints with run status |
| Immutability/compatibility | Immutable run/revision snapshots and blobs | Additive JSON v2, legacy in-memory prototype fallback, versioned processing config; no schema migration |

Prototype policy is deliberately small: keep one reference to the last confidently
associated observation embedding, not an EMA or an invented vector. Appearance model,
dimension, checksum and camera are validated before use. A missing intermediate mask
keeps the old prototype; a later moved detection can retain its identity. Prototype
updates do not silently commit anything to an approved revision. Accepted baselines
continue to use approved snapshots, and rejected changes stay outside them.

Final gates: **87 offline tests and 19 isolated PostgreSQL/Silo/Redis service tests
passed**, including the full fake two-capture E2E. Backend/scripts lint and format pass.
The Phase 5 suite covers stationary/moved objects, zero-IoU strong appearance, nearby
identical ambiguity, missing/reappearance, camera isolation/overhead, input reordering,
duplicate inputs/assignment, dimension normalization, scale gates/costs, missing vectors,
prototype checksum/camera validation, history pagination and unchanged prior evidence.

No packages/weights were downloaded, no containers started/recreated, no development
schema migrated and no original/revision was modified. Service fixtures create and
remove isolated test schemas/buckets/queues. Current real readiness still exits 2 with
`model_unavailable: missing yoloe checkpoint or expected SHA-256`. Fake contracts are
not pretrained-quality evidence. Existing upstream deprecation warnings remain visible.

**Phase 5 completed; stopped for review.** No Phase 6 or PointDiT P9 implementation.
Optional manual links remain deferred; automatic cross-camera identity is superseded.
For a real-model run, follow [operator setup](model-setup.md) or
[the Codex runbook](codex-real-inference-runbook.md).

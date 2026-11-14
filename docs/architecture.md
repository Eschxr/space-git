# Architecture

The Python 3.11 backend is one modular package: API, core configuration/logging,
domain, application, vision, infrastructure and workers. API imports remain CPU-only
and do not initialize models or connect to infrastructure. Phase 0 exposes liveness.

Later phases use PostgreSQL for durable state, MinIO/S3 for immutable originals and
artifacts, and Redis/RQ for JSON-serialized jobs carrying primitive IDs. Workers
resolve data server-side. Database status remains authoritative beyond Redis TTLs.
Vision runs Grounding DINO → SAM 2.1 → DINOv2 outside the API process.

Reconstruction is an independent Python 3.12 uv project, never a backend dependency
or shared workspace member. Future backend scheduling uses the string import path
`reconstruction_worker.worker.run_reconstruction` on a dedicated queue; only the
reconstruction worker resolves it. PointDiT yields per-view PLY, never fused geometry.

Every capture requires exactly cam_01..cam_04, with cam_04 fixed as overhead.
Original bytes remain immutable. Camera-local temporal tracks come first;
cross-view candidates preserve ambiguity and require reviewable, reversible links.
There is no calibration, registration, frontend, OpenUSD or metric movement.

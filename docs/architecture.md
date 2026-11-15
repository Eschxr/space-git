# Architecture

Python 3.11 FastAPI serves immutable four-image captures and reviewable semantic
history. PostgreSQL owns durable state; Silo/S3 stores immutable originals and
run-scoped derivatives; Redis/RQ carries versioned JSON job/run IDs. API imports
initialize no models or infrastructure connections and load no Torch, Ultralytics,
NumPy, SciPy or reconstruction modules. Models load only inside each spawned worker
job child, once for its four views. Real assets are local and verified, never fetched.

The active pipeline is YOLOE prompt-free extraction plus the retained DINOv2 adapter.
Canonical EXIF-corrected RGB copies supply original-pixel boxes/RLE masks; original
bytes stay unchanged. DINOv2 uses padded masked crops and normalized float32 vectors.
Missing masks/tiny regions retain explicit unavailable evidence. Per-camera stages
preserve successful outputs on failure and retain diagnostics. Retries create new
runs/keys rather than changing prior outputs. Database job/run status is authoritative
beyond Redis TTL; abrupt worker-host loss without a callback still needs operator
reconciliation. RQ uses SpawnWorker and JSONSerializer; the parent loads no models.

Scheduling freezes the four-view baseline under the environment-row lock and includes
its reference in the processing config hash. After extraction succeeds for all views,
an environment-row lock serializes association against that frozen state.
Hungarian assignment has explicit unmatched options, configurable scoring
and ambiguity margins. Immutable run snapshots carry chosen references and decisions;
mutable track registry fields are advisory. No automatic cross-camera physical-object
links exist. Missing observations retain last-visible evidence for possible reappearance.

Proposals describe image-view hypotheses, not physical facts. Review is separate from
commit. An environment lock serializes linear, idempotent revision commits; accepted
states copy only selected accepted proposals onto the parent state. Rejected events
remain queryable and cannot move the approved baseline. Committed proposal payloads,
revision rows, revision changes and revision snapshots are immutable. Stale baselines
must be reprocessed before a new commit. Historical physical-object history remains
readable without inventing view-local mappings.

Capture ingestion validates exactly cam_01..cam_04, filenames/signatures/MIME, dimensions,
EXIF, byte/pixel limits and timezone-aware timestamps. cam_04 always means overhead.
Capture rows transition uploading→ready/failed; ready requires all four frame rows.
Storage failures may retain orphan immutable blobs; no automatic evidence deletion.
S3 conditional puts reject overwrites; LocalStore atomically publishes checksum-verified
metadata/byte envelopes. Derivatives are environment-scoped. Signed S3 URLs expire.

Inspection uses static self-contained HTML and ZIP artifacts. JSON retains candidates,
chosen matches, canonical transforms, tracks, proposals, source/model hashes and package
provenance. Reports do not certify model accuracy. Cross-view association remains
explicitly unimplemented and optional; it does not block per-camera processing.

Highlight manifests select committed view events in their actual source image. The
CPU dense-grid utility performs recorded crop/flip/nearest-resize/pad transforms and
one shared XYZ/RGB/label validity filter. It records pixel/grid indices and conflicts;
it cannot recover correspondence from unordered PLY alone.

Reconstruction is a separate Python 3.12 uv project, never an API dependency or shared
workspace member. Future P9 integrates PointDiT at its dense point-map export boundary,
with independently acquired PointDiT/DINOv3 assets. It will emit per-view PLY and mapping
sidecars, without calibration, registration or fusion. This refactor provides contracts
and synthetic point-grid tests only. No frontend/OpenUSD is included.

Original Phase 0–4 architecture remains in Git and implementation-status history;
[the refactor plan](../CODEX_YOLOE_REFACTOR_PLAN.md) supersedes its vision/tracking path.

Image-history APIs expose capture attempts, review progress, approved revision evidence,
accepted per-track changes and endpoint comparisons. Review decisions append immutable
records while retaining current proposal status. Commits copy the final review decision
and source run/model/config/frame/artifact provenance in the same transaction as
approved snapshots. Older revisions derive explicitly tagged provenance on read.
Evidence readers sign URLs and retain unavailable asset references with explicit reasons.

The independently developed `frontend/` has a web app and its own local edge API.
Scene Tracker's typed capture/workflow/revision contracts provide the integration
boundary. The edge's metric scenes and branched commits have their own domain model.
Source capture/frame/camera IDs and canonical dimensions in revision evidence align
with highlight manifests for a future per-camera cloud viewer. PointDiT artifact
generation and pixel-to-point mapping remain the separate Phase 9 implementation.

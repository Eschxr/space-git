# Highlight contract and future PointDiT boundary

`GET /api/v1/captures/{id}/highlights?camera_id=cam_01&revision_id=...` returns
`schema_version: "1.0"`, capture/camera/frame, canonical image dimensions/orientation,
optional revision and signed image URL, plus regions with change/track/detection IDs,
type, before/after temporal role, canonical pixel box, mask key/URL and RGB color.
Without a revision filter, it selects all committed accepted events for that source
capture/camera. A revision filter selects events committed in that revision, not its
ancestors. Query both captures for separate before/after manifests.

Moves and appearance changes may have regions in both images. Appeared objects have
after-only regions; missing objects have before-only regions on their **last-visible
source capture** (which may precede the immediate comparison capture). No current mask
is invented. Missing masks return an explicit unavailable reason; the point colorizer
refuses to fabricate geometry. Historical object events without camera-local evidence
are excluded. Rejected/proposed/uncommitted changes are excluded.

`geometry/highlights.py` defines frozen JSON contracts. `geometry/point_grid.py` takes
dense image-indexed `(H,W,3)` XYZ and uint8 RGB, canonical masks and `GridTransform`:
source dimensions, integer crop rectangle, horizontal/vertical flips, resize dimensions
and padding. Transform order is crop → flip → nearest-neighbor resize → zero-pad.
No calibration is inferred. Shape/type/schema mismatches fail explicitly.

One finite-XYZ and optional boolean validity filter is applied to points, colors and
integer change labels, using row-major order. The sidecar preserves the exported
`grid_indices`, change labels and manifest region metadata, transform/order, point
count, capture/camera/frame/revision, model hash and overlap count. Lexically sorted
change ID then temporal role wins overlaps, independently of input ordering. Source
colors are copied; no-region output preserves them exactly.

`export_test_ply` exclusively creates ASCII highlighted PLY and JSON sidecar in a new
directory. The full fake smoke additionally exports source-colored synthetic clouds.
These are flat synthetic point grids, **not reconstructed 3D**. Neither regular PLY
vertex order nor the nth exported vertex can establish pixel correspondence by itself.

Future P9 must integrate the independent Python 3.12 PointDiT worker at its actual
dense-map boundary, record the identical image transform and apply all upstream
invalid/depth/sky filtering to every attribute together. It must preserve source PLY,
highlighted PLY and sidecar as per-camera artifacts and verify the real adapter uses
this mapping. PointDiT and gated DINOv3 access/runtime are separate manual gates.
No global alignment, registration or fused cloud follows from these contracts.

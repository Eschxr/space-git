# Surface reconstruction

SpaceGit archives the Floor and Radial A, B and C PointDiT outputs as individual PLYs. Its Three.js rig reads XYZ and RGB with `PLYLoader`, renders points with `BufferGeometry`, and applies each camera's existing position, rotation, axis conversion, and scale. The local FastAPI edge serves the archives and starts a separate CPU Open3D process. Reconstruction runs per view and retains the original file coordinates. The browser uses the same camera rig or single-file preview for each representation.

## Windows setup

From the `space-git` directory, install the surface worker in its own Python 3.13 environment. The camera edge and PointDiT retain their own environments.

```powershell
py -3.13 -m venv frontend/.cache/surface-env
.\frontend\.cache\surface-env\Scripts\python.exe -m pip install -r reconstruction/requirements-surface.txt
```

If the worker is in a different environment, set `SPACEGIT_SURFACE_PYTHON` to the absolute path of that environment's Python executable before starting the edge.

After installing the existing [frontend and camera edge dependencies](../README.md), start both services from `frontend` with `.\scripts\start.ps1 -Mode live`. Open [SpaceGit](http://127.0.0.1:3000/world) and connect in **Capture**. The standard start script still handles PointDiT generation through the existing WSL setup.

## Process and compare a scan

1. In **Reconstruct**, select a saved camera scan or use **Load PLY** to open an ASCII or binary point-cloud file. An imported PLY previews immediately. Connect the local edge to process it.
2. Select **Analyse scan** to inspect the point count, spacing, and recommended Poisson depth. **Reconstruction settings** includes outlier tolerance, optional voxel size, Poisson depth, low-density trimming, and gap support. Use the defaults for the first pass.
3. Click **Build smooth mesh** and follow the progress. **Cancel processing** stops the worker and retains completed results from previous runs. SpaceGit publishes the results after all views finish.
4. Switch between **Original points**, **Cleaned points**, and **Smooth mesh**. The camera and each view's transform stay in place. The projector can show any of these representations for a saved scan in **Project**. It opens on the latest applied mesh when one is available.
5. Expand **Mesh smoothing**, pick a preset, and click **Preview smoothing**. This reuses the supported Poisson surface. **Apply preview** makes it the current saved surface. **Discard preview** returns to the last applied result.
6. Select the view to export and download the original PLY, cleaned PLY, mesh PLY, or report. Single-file results use one view. Archived originals and uploaded source bytes are kept separately from the results.

Light uses 3 Taubin iterations and is the default. Balanced uses 8, Strong uses 15, and Off uses 0. Intensity adjusts the two Taubin passes. The worker limits vertex movement relative to point spacing, restricts movement on open edges, and checks for inverted or degenerate triangles. Use **Display settings** to adjust point size, opacity, mesh brightness, lighting, and the background without rerunning processing.

## Geometry and diagnostics

The worker validates the PLY header, coordinates, and optional RGB, then measures point spacing and its variation. It removes duplicate positions from the working cloud and can apply statistical outlier removal and voxel downsampling. Adaptive neighbourhoods estimate normals. Archived PointDiT views use their camera-local origins to orient normals. Standalone PLYs use neighbourhood orientation with a planar fallback where needed.

Screened Poisson creates indexed triangles. The worker filters low-density vertices and checks the distance to observations at vertices, edge midpoints, and face centroids. This limits unsupported faces and bridges between disconnected surfaces. After conservative smoothing, it transfers RGB from up to four nearby source points using inverse-distance weights and recalculates vertex normals. Each report records the input bounds, spacing distribution, removal counts, mesh size, component count, support fraction, settings, warnings, and processing time. Units remain those of the input file.

The mesh can close gaps supported by nearby points. Large occlusions and alignment errors between camera views can remain visible. Surface processing preserves existing camera transforms, so its results still depend on the calibration. Jobs run one at a time and accept up to 3 million points per input, within the 192 MiB PLY transfer limit. Poisson depth ranges from 5 to 11. Higher depth uses more memory and CPU time. Local job output is written under `frontend/data/live-surfaces` in live mode. Uploaded originals are in `inputs`, and processed files and reports are in `jobs`.

## CLI and checks

The optional CLI writes `original.ply`, `cleaned_pointcloud.ply`, `reconstructed_mesh.ply`, and `reconstruction_report.json` into a new directory. It also keeps `supported_mesh.ply` for derived smoothing runs.

```powershell
.\frontend\.cache\surface-env\Scripts\python.exe reconstruction/surface_cli.py input.ply output-directory --depth 9 --smoothing 3
.\frontend\.cache\surface-env\Scripts\python.exe -m unittest discover -s reconstruction/tests/surface -v
cd frontend
$env:SPACEGIT_TEST_SURFACES='1'
.\.venv\Scripts\python.exe -m pytest -q tests/edge/test_surface_api.py
```

For visual QA, orbit to a view that shows faces, furniture edges, and gaps between objects. Switch from original points to the mesh without moving the camera. Compare object scale, silhouettes, separation, color, and thin details. Then switch back to original points and compare the bounds and viewpoint. Inspect the report and toggle to cleaned points if a feature appears to be missing.

## Source files

- `reconstruction/surface_pipeline.py`, `surface_cli.py`, and `requirements-surface.txt` contain the geometry stages, worker entry point, and dependencies. `reconstruction/tests/surface/test_surface_pipeline.py` exercises the geometry on synthetic scans.
- `frontend/apps/edge/spacegit_edge/surfaces.py` handles uploads, jobs, cancellation, preview application, and exports. `main.py` registers it with the local edge. `frontend/tests/edge/test_surface_api.py` exercises the complete local API flow.
- Under `frontend/apps/web/app/world`, `surface-panel.tsx` and `surface-types.ts` define the controls and reports, and `edge.ts` connects them to the edge. `reconstruct-panel.tsx`, `camera-rig-viewer.tsx`, `project-panel.tsx`, and `world.css` integrate the processing and display controls.
- `frontend/apps/web/public/camera-rig/index.html` renders cleaned points and indexed meshes in the existing rig with the original camera transforms.

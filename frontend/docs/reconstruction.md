# Local COLMAP reconstruction

Install a Windows binary from the [official COLMAP releases](https://github.com/colmap/colmap/releases) or an appropriate Linux package. Set `SPACEGIT_COLMAP` to the trusted CLI executable or launcher, or put `colmap` on PATH. Follow the [COLMAP CLI guide](https://colmap.github.io/cli.html) to verify that it can run locally. The worker uses CPU feature extraction and matching, then incremental SfM. COLMAP 4.2.1 was used for the mesh and texture runs.

From the root, use the same `SPACEGIT_MODE` and `SPACEGIT_DATA` as the edge:

```powershell
$env:SPACEGIT_MODE = 'live'
$env:PYTHONPATH = 'apps/worker-3d'
.\.venv\Scripts\python.exe -m worker.main
```

```bash
SPACEGIT_MODE=live PYTHONPATH=apps/worker-3d .venv/bin/python -m worker.main
```

Run one worker per workspace. Cancel a pending job from **Worker jobs**. The running worker stops the active process when it sees the request. Starting the worker again marks interrupted jobs as failed or partial. Retry a failed, partial, or cancelled job with the same retained photos.

Upload overlapping JPEG/PNG views to one revision. Six is the queue minimum; 30–80 photos with varied viewpoint and strong texture are recommended. The worker checks dimensions, normalizes EXIF orientation in temporary copies, and bounds image size. The queue reports completed stages and real tail logs. A sparse output needs at least three registered images and 20 points. Choose a result:

| Mode | Actual output |
| --- | --- |
| Sparse | COLMAP sparse PLY. |
| CPU surface mesh | A Delaunay triangle mesh from sparse camera tracks, plus PLY, OBJ and GLB. This is a surface inferred from sparse measurements. |
| Textured CPU mesh | The same kind of surface, with COLMAP's atlas from undistorted registered photos, embedded in GLB and packaged with the textured OBJ. |
| Dense GPU | PatchMatch depth, fused dense PLY, Poisson surface, and portable mesh outputs when supported. |
| Textured dense GPU | Dense pipeline plus a baked atlas and textured GLB / OBJ archive when supported. |

COLMAP supplies the meshing and texturing here; a bounded NumPy converter packages its actual triangles and texture coordinates for the browser. Open3D can provide separate cloud processing, OpenMVS a separate multi-view pipeline, and Blender more export tools, but they are not prerequisites for these modes. The native path avoids adding multiple processing runtimes. Dense modes need a compatible GPU build and driver, at least 3 GiB free storage, and sufficient VRAM. Start with a small batch. If a later stage fails, the job is **partial** and exposes only completed artifacts, with the failure and logs.

In **Phone capture → Worker jobs**, preview an available point cloud or choose **Open mesh in 3D**. The mesh remains a separate visual layer attached to the photo revision. Orbit it in the raw frame or preview a transform over the wall. To set scale, enter a physical reference length and the corresponding span in mesh units. Scale does not establish camera or wall registration; use the independent position and rotation controls. Saving placement changes only the visual layer, not semantic objects or commit history.

If COLMAP is unavailable or a stage fails, the job reports why and keeps the originals. Fix the binary or improve capture coverage and queue again. Run a single worker per database and let it finish before closing it; jobs interrupted by a process crash may need to be queued again. Check [verification](verification.md) before choosing the GPU path on the tested workstation.

`python scripts/reconstruction-smoke.py --quality mesh_textured --images path/to/jpegs --output .cache/test-mesh` tests the complete CPU texture path. Omit `--images` to use deterministic rendered views. The script makes downsampled temporary copies and leaves originals untouched. Optional output files remain local.

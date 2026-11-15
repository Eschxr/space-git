# SpaceGit 3D

Version control for physical spaces. Save a measured wall layout, compare it with a later revision, and use a local projector and camera to guide and verify a restore. The browser shows the same scene as editable, metric Three.js geometry. Camera images stay on the workstation.

[Open the public read-only demo](https://spacegit-3d.vercel.app).

The local **Image history** workspace connects Scene Tracker to saved spaces,
immutable four-camera captures, YOLOE/DINOv2 processing, human review and approved
revisions. See the [integration guide](../docs/frontend-integration.md) for the
Docker API/worker and this system's ports: web **3101**, API **8001**, edge **8002**.
Copy `apps/web/.env.local.example` before building the integrated frontend.
After installing the Python edge dependencies, use
`scripts/start.ps1 -Mode live -Port 3101 -EdgePort 8002` to start its web and camera services.
Metric layouts, 3D viewers and projector tools remain available alongside image history.

The [Project demo MVP](../docs/project-demo-mvp.md) adds an Ollama prompt panel,
animated 3D additions, manual edits and undo. A live preview stays on the page
while the separate projector window is open. It uses your installed Ollama models;
quick-add controls also work without a model connection.

## New Worlds demo

Run `pnpm install --frozen-lockfile` and `pnpm dev`, then open [SpaceGit](http://127.0.0.1:3000) and click **Start Demo**. The guided flow captures a simulated room, compares two commits, opens the scene in 3D, and projects an animated virtual office. Open [Project](http://127.0.0.1:3000/project) on your second monitor for fullscreen output and an alignment pattern.

See the [New Worlds operator guide](docs/new-worlds.md) for the four-camera pole configuration, projection shortcuts, tests, and Vercel preview commands.

## Start on Windows

Use Node.js 24, pnpm 11.25.0 and 64-bit Python 3.12. From the repo root:

```powershell
pnpm install --frozen-lockfile
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/edge/requirements.txt
.\scripts\doctor.ps1
.\scripts\start.ps1 -Mode demo
```

Open [Hardware setup](http://127.0.0.1:3000/setup) and paste the printed local operator key. Go to **Live tracking → Replay one move**. The **DEMO / SIMULATED** badge and evidence provenance identify fixture output. Restart with `-Mode live` for real hardware. Both modes use separate databases and upload directories under `data/`.

On Windows, each live **Capture session** also replaces the contents of
`\\wsl.localhost\Ubuntu\home\wilson\test_images` with the available fresh frames,
named `01_radial_a.jpg`, `02_radial_b.jpg`, `03_radial_c.jpg`, and `04_floor.jpg`.
Numeric prefixes define the export order regardless of the preview sequence.
Previous sessions remain in local history.
Use `scripts/start.ps1 -Mode live -CaptureDirectory 'C:\path\to\images'` to change
the export folder. When starting the edge directly, set `SPACEGIT_CAPTURE_EXPORT_DIR`.

The Windows startup script also enables `SPACEGIT_POINTDIT_WSL=1`. Live capture then
requires four fresh views. After exporting them, it activates `/home/wilson/pointdit/.venv`
in Ubuntu as `wilson` and runs `bash scripts/demo_l_512.sh`. Keep the capture page open
while generation runs. The app confirms completion after verifying four updated PLYs
in `\\wsl.localhost\Ubuntu\home\wilson\pointdit\generation\pretrained-pointditl-512-mixdata-nodinov3-240c1a4f\test_images`.
Each PLY uses its image stem with `_pointcloud.ply`. Generation logs are kept beside
the local edge database in `pointdit/<session-id>.log`. Failure preserves captured
images and reports an error. The command has a 30-minute limit. The supplied script
reads the fixed `/home/wilson/test_images` path, so this workflow uses the default
capture directory. Direct edge launches without `SPACEGIT_POINTDIT_WSL=1` export
the available views without invoking PointDiT.

After successful PointDiT generation, **Reconstruct → Camera rig** displays the
supplied multi-camera HTML viewer inside SpaceGit. It loads `camera_poses NEWEST.json`
from the bundled `public/camera-rig/camera-poses.json` and the four latest generated
PLYs through authenticated edge requests. Viewer camera 1 is Floor, camera 2 is
Radial A, camera 3 is Radial B, and camera 4 is Radial C. **Reload PLY files** loads
the latest output again. The original viewer's orbit, camera view, transform gizmo,
denoise, config import/export, and PLY controls are available. **Scene revision**
opens the existing revision viewer. The embedded viewer bundles its original
Three.js 0.170.0 modules and license in `public/camera-rig/vendor`.

## Start on Linux

```bash
pnpm install --frozen-lockfile
python3.12 -m venv .venv
.venv/bin/python -m pip install -r apps/edge/requirements.txt
bash scripts/doctor.sh
bash scripts/start.sh demo          # or live
```

Linux uses OpenCV on V4L2. Display counting uses xrandr when available. On Wayland, confirm that you put the projector window on the extended display yourself. Keep the web UI at the default port 3000 and the loopback edge at 8000.

## Use it

| Task | Where to go |
| --- | --- |
| Calibrate and project | [Hardware guide](docs/hardware.md): open a webcam, define the work surface in the preview, and run automatic projector calibration on the extended display. The projected calibration points require no printed markers. |
| Save, compare, and restore | In **Live tracking**, box each textured object and save an observed layout on a branch. Select a revision and start restore with a measured workspace and validated projector. Save the verified result as a new child revision once all objects have held within tolerance. |
| Propose and merge | Create a branch from **History**. Edit objects, clearance or keep-out areas in **3D workspace** and commit. **Branch & merge** compares both wall plans and the candidate. Select conflict choices, preview again, then explicitly approve. |
| Inspect and exchange 3D | In **3D workspace**, orbit, select objects, edit position/dimensions, highlight changes from a revision, export a PNG, scene JSON or GLB, and import a SpaceGit export with its object IDs. |
| Capture with a phone | Configure the optional [HTTPS capture gateway](docs/deployment.md) and create a ten-minute link from **Phone capture**. Take or select several photos, retry individual failures, then optionally request reconstruction for local operator review. |
| Run real reconstruction | Install the official COLMAP command line and start the [worker](docs/reconstruction.md). Select at least six overlapping photos. Queue a sparse, CPU mesh, or textured CPU mesh job. GPU dense modes require a compatible host. Open a completed GLB in the independent visual layer and set its scale from a measured reference. |

```text
pnpm lint
pnpm test
pnpm build
python -m pytest -q -s
pnpm exec playwright install chromium
pnpm test:e2e
```

Run pytest with the repo virtual environment. Browser checks start a production web server and a fresh simulated edge on ports 3000 and 8000; stop any local SpaceGit instances first. Set `SPACEGIT_BROWSER` to use an existing Chrome/Chromium binary. Evidence, scope, and hardware limitations are in [verification](docs/verification.md). See [architecture](docs/architecture.md), [security and privacy](docs/security.md), [deployment](docs/deployment.md), [reconstruction](docs/reconstruction.md), and the [three-minute demo](docs/demo.md).

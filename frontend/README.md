# SpaceGit 3D

Version control for physical spaces. Save a measured wall layout, compare it with a later revision, and use a local projector and camera to guide and verify a restore. The browser shows the same scene as editable, metric Three.js geometry. Camera images stay on the workstation.

[Open the public read-only demo](https://spacegit-3d.vercel.app).

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

# New Worlds: run the demo and connect the pole

Run this from the repository root with Node 24 and pnpm 11.25.0:

```powershell
pnpm install --frozen-lockfile
pnpm build
pnpm start
```

Open [SpaceGit](http://127.0.0.1:3000) and select **Start Demo**. It advances through nine stages in about half a minute. Use **Pause demo** and **Next stage** to present at your own pace. The demo records two simulated sessions, saves both on the `guided-demo` branch, compares the mug's position, opens the study in 3D, then projects an office with three virtual agents. Demo history is stored in the browser. Camera images, hardware controls and live history stay on your workstation.

Connect the physical projector and press **Win+P → Extend**. Open [Project](http://127.0.0.1:3000/project), select **Detect displays**, and choose the external display. Select **Open projector window**, then click **Enter fullscreen** in that window. If display detection is unavailable, drag the projector window to the extended display first. Use Chrome or Edge if the in-app browser blocks pop-ups or display selection.

The Project tab controls the output while the projector window is fullscreen. Switch between **Virtual office**, **Physical world**, and **Test pattern**, adjust brightness, or use **Blackout**. The output keeps a 16:9 frame with black bars when needed. **Esc** exits fullscreen. For camera-aligned wall tracking, use **Calibrate for wall tracking** and follow the [hardware setup guide](hardware.md).

| Shortcut | Action |
| --- | --- |
| **D** | Start the guided demo |
| **F** | Enter fullscreen |
| **W** | Switch between the office and the selected physical scene |
| **G** | Toggle the alignment pattern |
| **B** | Toggle blackout |
| **H** | Hide or restore controls |
| **Space** | Play or pause the virtual agents |

The world engine validates agent, action, destination, and duration, then moves agents along fixed waypoints. It runs entirely in the browser without an LLM or API key. The office is a rendered simulation. The spatial assistant describes the recorded IDs and changes in the selected revisions.

## Use the physical rig

Start the live edge, then open [Capture](http://127.0.0.1:3000/world). Choose **Connect cameras**, then **Edit camera sequence** under **Pole layout**. Assign a detected device to each physical direction. Camera 4 faces down toward the floor. Repeat USB device names include the device index. Use the arrow controls to set the preview and capture order, then select **Save sequence** and **Start live previews**. If you plug in a camera while the page is open, choose **Refresh devices**.

You can optionally seed the assignments on the first run with `SPACEGIT_RIG_CAMERAS`. The entries correspond to 0°, 120°, 240°, and floor. Use a device index (0–15), `-` for an unassigned slot, or `primary` once to share the camera opened in Hardware Setup. Settings saved in Capture take precedence on later runs.

```powershell
$env:SPACEGIT_RIG_CAMERAS = 'primary,1,2,3'
.\scripts\start.ps1 -Mode live
```

If you assigned **Tracking camera from Setup**, open that device in **Hardware Setup** first. The web interface shows frame age at the edge. **Capture session** saves the available fresh frames and their sequence while the live monitor keeps refreshing. Select a recent session to inspect those saved frames. The cameras record independent views, so the feed timestamps can differ.

Use Version control to push an observed layout through the existing calibrated tracking workflow, pull the latest branch state from the edge, or inspect and resolve conflicts in Hardware Studio. Checkout loads a digital revision. Use the existing calibrated **Restore** workflow to guide a physical move.

Coordinates in Three.js are right-handed and Y-up. For a saved wall, X increases to the right, Y increases up from the lower edge, and +Z extends into the room. The renderer centers the wall horizontally and may fit its display scale. Distances are shown as metric measurements only for compatible calibrated revisions, or as synthetic metres for the fixture. Worker geometry keeps its own axes and units until separately placed and measured with the existing 3D workspace. In Reconstruct, open a worker artifact attached to a revision, or load a local PLY, GLB, or self-contained glTF with inline buffers. Select **Open projector view → Physical world** to project the loaded model or revision in the same window. PLY limits are 64 MB and 1.5 million vertices.

## Test and preview

```powershell
pnpm lint
pnpm test
pnpm build
.\.venv\Scripts\python.exe -m pytest -q
pnpm exec playwright install chromium
pnpm exec playwright test --config playwright.new-worlds.config.ts
```

The New Worlds browser suite starts the production web app on port 3100 and requires no edge service. The regular `pnpm test:e2e` suite still covers the hardware studio with a local simulated edge. Supply `SPACEGIT_BROWSER` to test against an installed Chromium browser. To test an existing public static deployment, set `SPACEGIT_TEST_URL` to its origin.

For an authenticated Vercel preview, run these commands at the repository root and select the existing `spacegit-3d` project when prompted:

```powershell
pnpm dlx vercel login
pnpm dlx vercel link --project spacegit-3d
pnpm dlx vercel deploy
```

The root Vercel configuration builds the static public version. No camera, local edge, reconstruction worker, or provider credentials are required for the hosted demo.

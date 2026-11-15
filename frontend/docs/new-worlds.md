# New Worlds: run the demo and connect the pole

Run this from the repository root with Node 24 and pnpm 11.25.0:

```powershell
pnpm install --frozen-lockfile
pnpm build
pnpm start
```

Open [SpaceGit](http://127.0.0.1:3000) and select **Start Demo**. It advances through eight stages in about half a minute. Use **Pause demo** and **Next stage** to present at your own pace. The demo records two simulated sessions, saves both on the `guided-demo` branch, compares the mug's position, and projects the reconstructed study. Demo history is stored in the browser. Camera images, hardware controls and live history stay on your workstation.

Connect the physical projector and press **Win+P → Extend**. Open [Project](http://127.0.0.1:3000/project), select **Detect displays**, and choose the external display. Select **Open projector window**, then click **Enter fullscreen** in that window. If display detection is unavailable, drag the projector window to the extended display first. Use Chrome or Edge if the in-app browser blocks pop-ups or display selection.

The Reconstruct tab shows the four-camera rig. **Open projector view** takes it directly to Project. Use **Model version** to choose a saved capture or a worker model, or select **Add 3D models** to open PLY, GLB or self-contained glTF files for the current Project session. Switch versions while the same projector window is open.

Each successful PointDiT capture saves its four PLY files together under `frontend/data/live-pointdit-models/<capture-id>`. The shared WSL output folder still holds the working files for the latest generation. **Save current PointDiT output** copies any complete set from that folder into the version list. Imported sets have their file date and no capture link. Files that an earlier run overwrote cannot be recovered from that folder. Versions use the configured camera poses in the rig viewer.

In **Reconstruct**, choose **Build smooth mesh** to process the saved views, or use **Load PLY** for a single scan. Switch between **Original points**, **Cleaned points**, and **Smooth mesh** in Reconstruct or on the projector for a saved camera scan. [Setup, settings, and export](surface-reconstruction.md).

Adjust brightness or use **Blackout** while the reconstruction is projected. The output keeps a 16:9 frame with black bars when needed. **Esc** exits fullscreen. For camera-aligned wall tracking, use **Calibrate for wall tracking** and follow the [hardware setup guide](hardware.md).

In **Projector chat**, type `add a red chair on the left`, or enter a description and click **Generate 3D object**. Ollama produces a low-poly object, and SpaceGit places it in the projected scene and saves it with that reconstruction version. Placement is approximate for point clouds. Save the current PointDiT output before generating onto a set of PLYs from the shared folder. For model generation and open-ended questions, install [Ollama for Windows](https://docs.ollama.com/windows), run `ollama pull qwen2.5:7b`, then start or restart the local SpaceGit edge and connect the workstation. Use `SPACEGIT_OLLAMA_MODEL` before starting the edge to select a different installed model. Basic commands such as `show current reconstruction` and `blackout` work offline.

Chairs, tables, sofas, beds, potted plants, lamps, and shelves use connected low-poly geometry. Describe the object, its style, color, and material, such as `add a round oak dining table with a black pedestal`. Other objects use approximate low-poly geometry. Each successful prompt shows its new object. Select **Show** beside an earlier result to display it again.

In **Generated objects**, choose **Edit position**, then grab the object in the 3D preview and drag it across the floor. Hold **Shift** while dragging to raise or lower it. The X, Y, and Z sliders also accept the wheel when focused. If the projector window is open, it mirrors the edit. **Save position** stores the move with that model version, and **Cancel** discards the draft. **Regenerate** rebuilds the object from its original description and keeps its saved position. **Restore original model** hides the additions in the preview, projector window, and sidebar. **Show generated objects** reopens the saved list and displays the selected result.

| Shortcut | Action |
| --- | --- |
| **D** | Start the guided demo |
| **F** | Enter fullscreen |
| **B** | Toggle blackout |
| **H** | Hide or restore controls |

The spatial assistant in layout history describes the recorded IDs and changes in the selected revisions.

## Use the physical rig

Start the live edge, then open [Capture](http://127.0.0.1:3000/world). Choose **Connect cameras**, then **Edit camera sequence** under **Pole layout**. Assign a detected device to each physical direction. Camera 4 faces down toward the floor. Repeat USB device names include the device index. Use the arrow controls to set the preview and capture order, then select **Save sequence** and **Start live previews**. If you plug in a camera while the page is open, choose **Refresh devices**.

You can optionally seed the assignments on the first run with `SPACEGIT_RIG_CAMERAS`. The entries correspond to 0°, 120°, 240°, and floor. Use a device index (0–15), `-` for an unassigned slot, or `primary` once to share the camera opened in Hardware Setup. Settings saved in Capture take precedence on later runs.

```powershell
$env:SPACEGIT_RIG_CAMERAS = 'primary,1,2,3'
.\scripts\start.ps1 -Mode live
```

If you assigned **Tracking camera from Setup**, open that device in **Hardware Setup** first. The web interface shows frame age at the edge. **Capture session** saves the available fresh frames and their sequence while the live monitor keeps refreshing. Select a recent session to inspect those saved frames. The cameras record independent views, so the feed timestamps can differ.

Open **Version control → Camera commits** to commit a complete saved session and inspect its four images and detected changes. Use **Layout revisions** for calibrated layouts and **Restore** in Hardware Studio to guide a physical move.

Coordinates in Three.js are right-handed and Y-up. Worker geometry keeps its own scale. Position offsets in Project use scene units. PLY limits are 64 MB and 1.5 million vertices.

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

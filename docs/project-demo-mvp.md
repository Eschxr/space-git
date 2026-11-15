# Project demo MVP

`/project` is the demo control page. The left side previews the output, and the
right side contains the Ollama scene assistant, object controls and existing
projector settings. Open a separate projector window, move it to your extended
display and enter fullscreen there. The page keeps a live video of its WebGL
canvas. There is one renderer and simulation; the preview cannot drift to a
different camera. Grid and blackout apply to both outputs.

## Run locally

From `frontend/`, using the existing pinned dependencies:

```powershell
pnpm install --frozen-lockfile
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r apps/edge/requirements.txt
# Optional: point to the host running your existing Ollama models.
$env:SPACEGIT_OLLAMA_URL = 'http://127.0.0.1:11434'
# Existing PointDiT output folder on this laptop (Windows or WSL paths work).
$env:SPACEGIT_POINTDIT_OUTPUT_DIR = 'C:/path/to/pointdit/output'
.\scripts\start.ps1 -Mode live -Port 3101 -EdgePort 8002
```

Open `http://127.0.0.1:3101/project`. Start your existing Ollama service, click
**Connect local edge**, and select an installed chat model. **Refresh models**
reloads the list. Alternatively, **Connect and load reconstruction** connects the
same local edge and loads the current point cloud. The browser connects only to the authenticated Python edge;
the edge uses Ollama's native `/api/tags` and `/api/chat`. Remote Ollama hosts
can be configured in the edge's environment. No models are installed, pulled
or selected through an external paid service by the application.

1. When connected, Project automatically loads the current `cam_01` reconstruction.
   Select **Reconstruction view** to switch independently among `cam_01` through
   `cam_04` (overhead). **Load current reconstruction** retries or refreshes the
   selected view and preserves added objects. The configured folder must contain
   `01_radial_a_pointcloud.ply`, `02_radial_b_pointcloud.ply`,
   `03_radial_c_pointcloud.ply` and/or `04_floor_pointcloud.ply` for the views you use.
   These are reads of existing outputs; opening Project does not capture cameras,
   regenerate PointDiT or merge point clouds. Missing/invalid files show an error
   without falling back to simulated geometry.
   Use **Open reconstructed scene** to load one PLY, GLB or self-contained glTF.
   You can also send a loaded model from Reconstruct with **Open projector view**.
   The virtual office remains an explicitly labeled simulation for rehearsals.
2. Try “Add a blue floating sphere”, then “Make it spin and move it left”.
   Text conversation and the current object state travel to Ollama. Source
   images and reconstruction bytes are not sent. The model does not see the room.
3. Quick-add a sphere, cube, torus or cone without a model connection. Select an
   object to adjust its color, animation, relative position and size. Available
   animations are spin, float and pulse. Pause, remove, clear and undo are provided.
4. Open the projector window. Keep the Project page open to edit the shared output.
   Closing the output window returns the renderer to the page.

For testing on another laptop, check out `codex/project-reconstruction-demo`, run
the setup above, and replace the output path with that laptop's existing files.
If its PointDiT outputs use other filenames, open the desired file directly.
Ollama must already have a chat model installed that supports structured output.
No Ollama credentials or model files are committed. The environment variables
above belong to the Python edge process; changing them requires restarting it.

## Contract and limits

The model returns a complete bounded list of up to 12 decorative objects plus a
reply, constrained with a JSON schema. Python validates IDs, uniqueness, shapes,
animations, colors, positions, sizes and response completion. The browser validates
the object plan again before applying it. Models cannot supply executable code,
asset URLs, file paths or changes to source geometry. Failed, incomplete or invalid
responses leave the current scene and prompt intact, without a simulated reply.
Only installed model names are accepted. Requests time out after two minutes.
Official protocol: [Ollama structured outputs](https://ollama.com/blog/structured-outputs)
and [API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md).

Positions use relative viewer coordinates, scaled to the loaded source's bounds.
They do not represent detected surfaces, physical measurements or registered room
positions. PLYs remain independent per-view sources; this MVP adds no calibration,
registration, reconstruction inference or fusion. Object generation means built-in
procedural geometry, not text-to-mesh generation. Voice input, image planes, imported
decorative GLBs, surface anchoring and saved projects are future extensions.

Edits and conversation last for the mounted Project session; reload/navigation
resets them. Undo retains the last 40 object states. Original files and committed
history are untouched. Reduced-motion preferences disable added animations in the
office renderer. Live preview requires canvas capture (verified in Chrome); output
still works if capture is unavailable and a visible message explains the limitation.

## Checks

```powershell
pnpm lint
pnpm test
pnpm build
uv run --python .venv/Scripts/python.exe --no-project python -m pytest -q tests/edge
$env:SPACEGIT_TEST_URL = 'http://127.0.0.1:3101'
$env:SPACEGIT_TEST_EDGE_URL = 'http://127.0.0.1:8002'
$env:SPACEGIT_BROWSER = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
pnpm exec playwright test --config playwright.new-worlds.config.ts
```

The browser's model responses and the Python Ollama transport are offline fixtures.
These verify contracts and scene editing, not real language-model quality or physical
projector hardware. The mirror test samples decoded video pixels and checks for the
colored added object, rather than only checking that an empty video element exists.

# Real-data workspace

Start the Python edge in live mode and open `/world`. The workspace has Capture,
Version control, Reconstruct and Project. There is no simulated workspace, seeded
browser history, virtual office or automatic walkthrough.

## Capture and history

Connect the local edge, assign the four fixed-role cameras and start live previews.
cam_01..cam_03 are side views; cam_04 is overhead. Capture is disabled without live
frames. Missing frames and disconnected services remain explicit. Original capture
bytes and accepted revisions are preserved. Version control reads persisted edge
history and never manufactures a capture or revision in browser storage.

## Project

Configure `SPACEGIT_POINTDIT_OUTPUT_DIR` on the edge to the existing PointDiT output
folder. Connect and load the current reconstruction, or open a PLY/GLB/self-contained
glTF file. Choose one camera view at a time; there is no registration or cloud fusion.
Select an installed Ollama chat model to add or modify decorative 3D features.
Scene editing stays disabled until real source geometry is loaded. Manual controls
and undo are available on that loaded geometry. No source geometry is modified.

Detect displays, choose the connected projector, open the output window and enter
fullscreen there. The page keeps a live preview of the same renderer. Brightness,
contrast, blackout and the alignment grid remain available as projector tools.

| Key | Action |
| --- | --- |
| F | Fullscreen |
| G | Alignment grid |
| B | Blackout |
| Space | Pause/resume added animations |
| Esc | Exit presentation |

See [Project setup](../../docs/project-demo-mvp.md) for exact startup commands and
Ollama/output-folder configuration. Normal start scripts accept live mode only.
Missing source files, unavailable models and invalid model replies report errors.
Offline fixtures remain isolated in the test suite; they do not certify pretrained
quality or physical hardware.

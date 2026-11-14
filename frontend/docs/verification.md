# Verification and acceptance

## Markerless MVP

| Acceptance | Status | Evidence |
| --- | --- | --- |
| AC-01–03 Windows startup, webcam and diagnostics | PASS | Local Setup returned HTTP 200. Edge opened camera index 1 at 1280 × 720 in the opt-in browser test. A delivered frame was entirely dark, which the diagnostics classified as Unsuitable. The edge reported 14.8 ms of processing for that sample. The FPS window had not yet settled. |
| AC-04–05 Select and track an ordinary object | PASS | Integration test registers a textured object from generated camera frames, tracks a move without tags, loses the observation under occlusion, and reacquires the same identity. Real object trials remain separate. |
| AC-06–08 Commit, diff and restore geometry | PASS | The markerless integration test records two immutable observations, validates projector geometry, and restores the earlier pose. Existing tests check diffs and revision integrity. |
| AC-09–12 Guidance, loss, dwell and restore history | PASS | Simulated browser replay renders the green guidance. Markerless integration checks that loss blanks the overlay and that reacquisition plus dwell allows an explicit verified child revision. |
| AC-13–14 Parametric editing, GLB import/export and screenshot | PASS | Production browser tests cover editing, GLB round-trip, loading a separate reconstructed mesh, and downloading a PNG. |
| AC-15 Real CPU reconstruction | PASS | COLMAP 4.2.1 registered 10/10 licensed photos, exported 6,853 sparse points, and generated a textured 10,033-triangle GLB (3,110,104 bytes). The smoke test took 38.25 s. Scale remains arbitrary until reference scaling. |
| AC-16 Secure phone upload | PASS | Phone-sized browser test paired over temporary loopback HTTPS, uploaded photos to the selected revision, retried a failed upload, and checked that operator routes were isolated. |
| AC-17 Branch and merge | PASS | Browser and Python checks cover the base/current/candidate review, constraints, stale-candidate rejection and explicit approval. |
| AC-18 Read-only demo candidate | PASS | The local public export exercised nine routes and fixture replay without external requests or an edge WebSocket. |
| AC-19 English UI | PASS | Source check found no Han characters in the app or static public assets. Browser checks exercised English controls. |
| AC-20 Builds and automated checks | PASS | `pnpm lint`, `pnpm test`, `pnpm build`, the static public build, and `.venv\Scripts\python.exe -m pytest -q` passed. Playwright passed six application tests with HTTPS and the reconstructed GLB enabled, plus one separate opt-in webcam test. |
| HW-01 Physical display selection and fullscreen output | BLOCKED | Windows reported one active display during this run. No projection surface was observed. |
| HW-02 Actual camera-to-projector calibration | NOT TESTED | Acknowledged projected-dot detection, independent reprojection checks, a crop and display invalidation passed with generated observations. |
| HW-03–05 Physical overlay, restore, accuracy and p50/p95 latency | NOT TESTED | Requires a lit scene, textured object, projector and physical measurements. Frame processing time does not measure camera-to-light latency. |
| HW-06 Physical handset capture | NOT TESTED | A real phone and a gateway with handset-trusted HTTPS are still required. |
| GPU dense PatchMatch | BLOCKED | Earlier Windows CUDA trials reproduced the native failure below. The CPU path was re-run successfully for this MVP. |
| Remote deployment | NOT TESTED | The candidate was built and tested locally. No account or project approval was established for publication. |

Screenshots from the production browser run are available for [Landing](screenshots/mvp/landing.png), [3D workspace](screenshots/mvp/studio.png), [Guidance replay](screenshots/mvp/verified-demo.png), [Merge review](screenshots/mvp/spatial-merge.png), [Mobile capture](screenshots/mvp/capture-mobile.png), and [Reconstructed mesh](screenshots/mvp/reconstructed-mesh.png).

## Phase 2

Verified on Windows on 11 November 2026, on `phase2/spatial-computing`. The Phase 1 baseline was `32afacf`. The [public demo](https://spacegit-3d.vercel.app) is a separate static build; hardware stays on loopback.

The published Phase 2 build was `dpl_2uJuFS7TgQvkxCGnV45swKjxRqQy`, from web sources at `a99c5f3b74ca22b6a6c457f3ca4e148ead337f98`. It reached READY and passed the production Chrome check. The later visual labels and restore-button gating passed locally but were not published: automatic approval review rejected the follow-up source upload. The final local out-of-footprint guard is edge-only and was never part of the public deployment.

| Feature | Status | Evidence |
| --- | --- | --- |
| Local webcam preview and device selection | PASS | Chrome opened camera 0 at 1280×720 and decoded the authorized live preview. No frames were saved. |
| Print-ready markers and optional intrinsics | PARTIAL | ArUco and checkerboard generators are supplied. A known synthetic lens fit recovered the camera matrix and corrected pixel coordinates. A printed board and physical lens fit are not yet tested. |
| Camera / projector calibration and monitor selection | PARTIAL | Synthetic API integration ran all 12 acknowledged correspondences and saved a fit bound to the camera and display. It rejected a changed framebuffer, a stale cross, and a report without acknowledgment. Only one physical display was present; external projection and screen selection on multiple actual monitors remain untested. |
| Marker tracking, green direction and reacquisition | PARTIAL | ArUco generated-frame detection, direction endpoints, dwell reset, low-confidence blanking and synthetic calibration invalidation passed. Real marker motion and projected alignment were not tested. |
| Dwell and verified layout revision | PARTIAL | Custom tolerance/dwell, fixture replay, and transaction tests passed. A full live plan writes measured positions as a new child on a dedicated branch; the original branch and history remain unchanged. No physical deployment was run. |
| Wall error, repeatability, stability and timing | PARTIAL | The diagnostics UI and benchmark procedures separate ruler error, pose spread, and software callback timing. No physical p50/p95 latency, repeatability, wall error or tracking-jitter samples were collected. |
| Commit, diff, history and restore preview | PASS | Immutable history and stale-tip rejection passed in SQLite and Chrome. Hardware restore is covered separately above. |
| Spatial Merge with placement rules | PASS | Branch conflict, independent field changes, keep-outs, clearance, side-by-side plans, changed-candidate rejection and explicit two-parent approval passed. |
| Semantic 3D, GLB round trip and visual placement | PASS | Browser checks preserved stable object IDs, opened the real textured GLB in a separate viewer, and applied a reference scale. API tests confirmed visual placement cannot rewrite commits. |
| Sparse reconstruction, CPU mesh and texture | PASS | COLMAP 4.2.1 ran on 10 licensed photographs. CPU mesh: 10,001 triangles in 28.30 s. CPU texture: all 10 views, 6,871 sparse points, 9,991 triangles, 3,124,232-byte textured GLB and OBJ + atlas archive in 34.72 s. Both timings include image preparation and upload. |
| GPU dense cloud, Poisson and dense texture | BLOCKED | Official CUDA 4.2.1 stopped in native PatchMatch (Windows exit 3221226505) both on the real photos and on the smaller rendered fixture with explicit GPU selection. The worker correctly reported partial results and retained sparse PLY. No driver changes or dense output were claimed. |
| HTTPS mobile session and reconstruction request | PARTIAL | Phone-sized Chrome used a temporary TLS gateway to upload six photos, retry one interruption, and request a CPU mesh. The operator route remained inaccessible on that gateway. Orientation and dimensions were verified independently; an actual handset camera and trusted handset gateway remain untested. |
| Read-only public web and fixture replay | PASS | Production Chrome checks loaded all nine routes and played the labeled replay with no off-origin requests, hardware WebSocket, or page errors. |

Commands run: `pnpm lint` (ESLint and TypeScript), `pnpm test`, `pnpm build`, `python -m pytest -q -s` (16 passed), `pnpm test:e2e` with the HTTPS and real GLB checks enabled (six passed), and the opt-in `hardware.spec.ts` (one passed). The edge tests emitted one upstream Starlette/HTTPX deprecation warning.

The synthetic solver measured 0.0000143 px mean / 0.0000239 px worst; fixture timestamp delivery was about 0 ms median / 0.97 ms p95 in-process. Neither is a physical accuracy or latency measurement. The next on-site test needs an extended projector, a measured marked wall, a phone and the [hardware measurement procedure](hardware.md).

[Spatial Merge](screenshots/phase2/spatial-merge.png) · [Textured CPU mesh](screenshots/phase2/reconstructed-mesh.png) · [Phone-sized capture](screenshots/phase2/capture-mobile.png) · [Bundled rehearsal](screenshots/phase2/public-rehearsal.png)

## Phase 1 baseline

Verified on Windows on 11 November 2026. Read-only public demo: [spacegit-3d.vercel.app](https://spacegit-3d.vercel.app). The production build was inspected in Chrome. Landing, studio, 3D, setup, and capture returned HTTP 200; the studio rendered the simulated wall and accepted object selection. No off-origin requests, WebSockets, or browser errors were observed.

| Check | Result |
| --- | --- |
| `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm test`, `pnpm build` | Passed with the deployment lockfile. All nine requested routes built. |
| `python -m pytest -q -s` | Six tests passed. Includes generated ArUco detection, pose order/outlier handling, independent calibration checks, lost tracking and dwell, immutable history, merge, restricted uploads, and missing COLMAP. |
| `pnpm test:e2e` | Two fixture tests passed in Chrome. Landing, six-card WebGL scene, guidance replay and persisted verification, GLB import/export, branch-tip commit, object diff and phone-sized upload. |
| `SPACEGIT_TEST_LIVE=1 pnpm test:e2e hardware.spec.ts` | Passed. Real camera index 0 opened at 1280×720, the browser decoded a live preview, no anchors were detected, and projection remained `SETUP_REQUIRED`. No frames were saved. |
| `SPACEGIT_TEST_HTTPS=1 pnpm test:e2e phone-https.spec.ts` | Passed. Mobile viewport, local TLS test gateway, paired upload assigned to the intended revision, operator routes unavailable on the gateway. The test uses a disposable certificate. |
| `python scripts/reconstruction-smoke.py` | Real COLMAP 4.2.1 CPU run on rendered fixture images: 14/14 views registered, 7,683 points, 115,433-byte PLY, 14.22 seconds including fixture generation and upload. The download required authorization. |
| `python scripts/reconstruction-smoke.py --images <folder>` | Real COLMAP 4.2.1 CPU run on 10 photographs from Matthew Guertin's [CC BY 4.0 dataset](https://github.com/Matt1Up/tree-photogrammetry-dataset): 10/10 registered, 6,853 points, 102,983-byte PLY, 24.58 seconds including downsampling and upload. No supplied camera poses or point cloud were used. |
| `node scripts/check-public.mjs https://spacegit-3d.vercel.app` | Passed through installed Chrome. The public site and the local edge are separate builds. |

The noiseless synthetic calibration check measured 0.0000143 px mean / 0.0000239 px worst residual. The in-process fixture timestamp to test client was approximately 0 ms median / 0.99 ms p95 in the final edge run. These numbers measure solver consistency and in-process fixture delivery, not wall error, sensor exposure, or the physical camera-to-projector path.

[Landing screenshot](screenshots/landing.png) · [3D studio](screenshots/studio.png) · [Simulated verification](screenshots/verified-demo.png) · [Phone-sized capture](screenshots/capture-mobile.png)

The workstation reported one active display, an RTX 4060 Laptop GPU with driver-reported CUDA 12.6, and no ffmpeg. COLMAP 4.2.1 was downloaded from the official release and checksum-verified in the ignored workspace cache for the smoke test. This does not install COLMAP globally. No physical projector, prepared marker wall, configured phone gateway, or test handset was available. Linux instructions are supplied; this verification was on Windows.

| ID | Tier | Status | Evidence and remaining gate |
| --- | --- | --- | --- |
| SG-01 | P0 | PASS | Physical camera selected; authorized browser preview decoded live at 1280×720. |
| SG-02 | P0 | BLOCKED | Fullscreen projector route and heartbeat implemented. Only one active display; no external projection verified. |
| SG-03 | P0 | PARTIAL | Four ArUco anchors and six fit/six validation correspondences implemented. Synthetic solver passed and rejects missing anchors or bad independent validation; no on-wall calibration. |
| SG-04 | P0 | PARTIAL | OpenCV detected four distinct object IDs in generated frames; smoothing, sequence, loss and drift tests passed. No observed physical card motion. |
| SG-05 | P0 | PARTIAL | Green arrow, target, displacement and progress driven by pose replay in Chrome. No observed projection on the wall. |
| SG-06 | P0 | PARTIAL | Continuous 0.7 s dwell, tolerance, and persisted evidence tested. Physical verification accuracy and latency are unmeasured. |
| SG-07 | P0 | PASS | SQLite immutable snapshots, revision parents, stale-tip rejection and browser object diff tested. |
| SG-08 | P0 | PARTIAL | Restored an earlier commit and persisted verification in fixture mode. Real on-wall restore blocked by hardware. |
| SG-09 | P0 | PASS | Six metric boxes, Three.js wall, orbit, selection, pose editing and branch commit. Browser exercised selection and position edit. |
| SG-10 | P0 | PARTIAL | Phone-width Chrome uploaded through a temporary HTTPS gateway to the correct revision. Actual handset camera and a handset-trusted gateway are unverified. |
| SG-11 | P0 | PASS | Public HTTPS demo verified in Chrome with no edge access. |
| SG-12 | P1 | PASS | Same-object conflict, overlapping footprint, valid deterministic candidate, explicit approval and two-parent merge covered. |
| SG-13 | P1 | PASS | COLMAP sparse pipeline and private PLY passed on rendered views and ten licensed photographs. Failure preserves inputs. Dense reconstruction and wall registration are not implemented. |
| SG-14 | P1 | PASS | GLB export/import checked in Chrome with six stable object IDs; scene JSON also supported. |
| SG-15 | P1 | PARTIAL | Ten-minute upload-only revision capability and private HTTPS proxy config. Hosted identity and cloud relay are not implemented. |
| SG-16 | P1 | PASS | Loopback studio, bundled assets, local SQLite and fixture operations use no hosted services. |
| SG-17 | P2 | BLOCKED | No LiDAR adapter or compatible physical source verified. |
| SG-18 | P2 | BLOCKED | No 3DGS appearance layer or splat assets included. |

Next physical acceptance run: attach an extended projector, print and measure the four anchor tags, validate the crosses, then log median and p95 camera-to-projected-overlay latency and measured wall residuals. Verify at least five of six cards and an occlusion/reconnect. Separately pair a real phone via the HTTPS gateway, capture a new photo, and confirm that it appears on the intended revision.

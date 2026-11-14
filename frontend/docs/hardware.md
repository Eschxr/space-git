# Camera and projector setup

## Markerless setup

1. Run `scripts/start.ps1 -Mode live`, open [Setup](http://127.0.0.1:3000/setup), and enter the local operator key. Select the camera and open it. The resolution selector requests a format; the status reports what the driver actually negotiated.
2. Aim the camera at the whole flat work surface. Choose **Define camera workspace**, then click its top-left, top-right, bottom-right, and bottom-left corners in the raw preview. Enter both measured dimensions for positions in meters. Leaving them blank gives normalized coordinates for preview and tracking. Save the workspace.
3. For physical projection, extend Windows onto the projector. In **Open projector**, detect displays and choose the projector, or move the window onto it manually. Enter fullscreen. The test frame confirms where the browser is displaying.
4. Frame the whole projected image in the webcam and choose **Automatic calibration**. The projector alternates dark frames with six fit points and six independent check points. Hold the camera, projector, and surface still. The validated profile crops and straightens the preview. Use **Manual calibration** to click the same projected references if automatic detection cannot isolate the bright dots. Neither flow needs printed markers.
5. In **Live tracking**, choose **Select object**, box a textured planar object with two opposite corners, name it, and start tracking. Keep the box tight and include stable detail. Use **Reselect** if an object stays lost. Choose its prior identity when resuming after a service restart. Feature references remain in memory for the local session.
6. With measured dimensions, **Commit observed layout** saves current confident poses. An object omitted from observations retains its previously saved pose with unobserved provenance. Remove a confirmed missing object explicitly in the 3D editor. Estimated boxes produce approximate planar dimensions and a default 20 mm display depth, which you can edit in the 3D workspace.
7. Select an earlier revision in **Live tracking**, set tolerance and dwell, and start restore. Follow the green outline and arrow. Occlusion, weak matches, stale observations, or detected camera movement pause guidance and reset dwell. After all objects hold their targets, select **Save verified restore** to create a child revision.

### Camera diagnostics

FPS measures delivered frames over a rolling two-second window. The shortfall compares that rate with the driver's reported FPS when available and is an estimate, not a hardware drop counter. Brightness and the variance of the grayscale Laplacian use a 320 × 180 sample. Pixels below 25 and above 245 count as dark and clipped bright. Edge processing time covers work after frame receipt, not sensor or physical projector latency.

The image is **Unsuitable** below brightness 30, above 230, or below 5 FPS. It is **Limited** below sharpness 35, outside brightness 55–205, or below 12 FPS. **Excellent** requires sharpness of at least 100, brightness 70–190, and at least 22 FPS. Other samples are **Good**. These are setup heuristics. Texture and stable inlier matches determine whether a particular object can be tracked.

Planar calibration depends on fixed camera, surface, and projector geometry. Software rejects changed capture/display signatures and detects sufficiently large camera shifts when static background features are visible. A featureless wall or a moved projector lens may require you to notice the change and recalibrate. Camera-only corner validation checks geometry; projector validation reports pixel residuals. Use the physical reference target and a ruler for an independent accuracy measurement.

## Optional measured ArUco mode

```text
                  matte flat wall / viewed from camera
            (3) +-------------------------------+ (2)
                |          [17]   [18]          |
                |   [19]           [20]         |  span Y
                |          [21]          [22]   |
            (0) +-------------------------------+ (1)
                             span X

        fixed webcam --> whole wall    projector --> same plane
```

1. Mount a webcam where it sees all four anchors and the cards. Avoid glare and automatic zoom. Aim a projector at the same wall. On Windows press **Win+P → Extend**. In the projector tab, **Detect displays** in supporting Chromium browsers and select the projector. If the browser denies window-management permission or does not support it, move the window with **Win+Shift+Left/Right** (or your Linux window manager) and enter fullscreen on the current display. Confirm visually that the output is on the wall.
2. Generate a marker sheet with `python scripts/markers.py` inside the virtual environment. Print at actual size. Measure the black edge in meters and enter it; the default form value may differ from your print. Place IDs 0/1/2/3 upright on the corners of a measured rectangle in the order in the diagram. Enter the center-to-center distances. Mount object tags at the centers of their cards with the same orientation.
3. Start live mode and connect in **Hardware setup**. Select a camera by name and choose a marker dictionary, then open the camera. Refresh the list after plugging in a camera. Confirm the image, four anchor IDs, and actual frame resolution in the preview.
4. Optionally generate a lens target with `python scripts/checkerboard.py`. Print it at actual size and attach it to a rigid board. In Setup, sample at least ten views spanning the image and different tilts and distances. A fit requires varied views, at most 1.5 px global RMS and at most 2.5 px worst-view RMS. Saving it invalidates wall calibration; run the wall wizard again. During the wall fit and tracking, the edge corrects camera pixels using the saved lens calibration only when the camera signature matches.
5. In Setup enable **Use ArUco anchors for a measured wall**. Open the projector in fullscreen on the extended display. Aim the beam so its targets fall inside the anchor rectangle, enter the measured spans and black marker edge, then select **Automatic calibration**.
   Use **Manual calibration** if a dot is hard to detect. Wait for each cross, click its center in the camera preview or enter its pixel coordinates, and validate all twelve points. The residual plot shows projector pixels, with vectors enlarged for visibility.
6. In **Check accuracy on the wall**, select a reference point inside the measured area. Use a ruler and square to measure where the projected center actually lands relative to anchor 0. Enter measured X and Y; Setup stores the signed offsets and radial error with the calibration ID.
7. Add cards in **3D workspace** and enter real dimensions. **Commit observed poses** saves current camera measurements. Move a card, then use **History → Review restore settings** to choose the target revision and configure 5–75 mm tolerance and 0.35–5 s dwell. Yaw tolerance is 0.12 rad (about 7°). The arrow should follow the observed card and disappear on loss or drift. A whole live deployment waits for all cards to hold together before saving a new measured child revision on a dedicated `verified-…` branch. A one-card plan for a larger scene records evidence for that card only.

If tracking is lost, uncover the marker, move your hand away, and reduce glare. Dwell restarts on reacquisition; a stale frame never advances dwell. Loss of fullscreen, a stale projector heartbeat, a changed camera signature, moved/missing anchors, or changed display geometry stops live guidance. The edge cannot detect physical beam occlusion or a projector whose optics moved while the operating-system display identity stayed the same. Rerun validation after any change in projector position, zoom or keystone. Recalibrate Phase 1 wall profiles once to bind them to the display fingerprint. In a card swap, move the blocking card to a temporary free position before following the target.

The projector emits light even where the canvas is black. Check contrast at the actual wall in demo lighting. Homography is planar, so keep marker faces close to the wall. Do not infer depth, touch, or safe drilling coordinates from this setup.

## Physical acceptance measurements

Record camera index/resolution, projector display/framebuffer, mount and distance, anchor sizes, focus, lighting, tolerance and dwell for each trial. Use the same physical references throughout.

- **Target error and repeatability:** choose at least three reference points, including positions near opposite corners; mark them with a ruler before projection. Run at least three fresh calibrations. Record the target and observed centers in a CSV with headers `run,x_expected_m,y_expected_m,x_observed_m,y_observed_m`. Run `python scripts/spatial-bench.py repeatability path/to/wall.csv`. This reports error versus the ruler target and spread around each reference's measured median across runs.
- **Tracking stability:** immobilize a marked card for at least eight seconds with the display registered. In Setup record the marker, sample count and radial spread p50/p95. Repeat at several distances and near all corners. Repeat with brief occlusion, a moved anchor and unplug/reconnect; any guidance during a bad frame fails the check.
- **Software timing:** run guidance with the projector active and collect the panel's camera-read-to-browser-render callback p50/p95 and sample count. This excludes sensor exposure/buffering and the projector's own refresh and processing.
- **Physical latency:** frame both the card and projected arrow with an independent fixed high-frame-rate camera (120 or 240 fps where available). Make at least ten separate abrupt card movements within the beam. For each movement, annotate the first frame in which the card crosses a visible reference and the first frame showing the corresponding arrow update. Write a CSV with `motion_frame,arrow_frame` and run `python scripts/spatial-bench.py latency path/to/timing.csv --fps 240`, using the recording's actual frame rate. Save the p50/p95, sample count and per-frame measurement resolution. This includes camera capture, tracking, transport, browser, and actual projection; the software callback alone cannot provide that result.

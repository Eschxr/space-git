# SpaceGit — media captions, demo script and judge notes

Team: **ZygomorphicMereOtter**, Durham University.
Primary theme: **Marshall Wace Challenge 1 — New Worlds**.

Draft companion to [submission copy](devpost-submission.md). Capture actual screens
and clearly label real inference, simulation and any optional WSL demonstration.
This document prepares the writing; it does not create screenshots or record/upload
a video. Use your own room imagery or preserve permission and source attribution.

## Gallery sequence and captions

Use up to six strong images rather than filling all 15 slots. Export JPG/PNG/GIF at
3:2 where practical, under 5 MB each, without cropping away the evidence labels.

| Order | Suggested image | Copy-ready caption / alt text |
| --- | --- | --- |
| 1 | Actual workspace hero showing four source images | **A history for your space.** Four fixed camera views become a capture with retained source images and hashes. |
| 2 | Actual proposed-change card with crop or run overlay | **Inspect the evidence.** YOLOE and DINOv2 propose camera-local changes; the source image, crop and run overlay support human review. |
| 3 | Actual review and selected-commit controls | **Approval is explicit.** Record a decision, select accepted proposals, and commit only the changes you want in approved history. |
| 4 | An actual committed revision and comparison | **Return to an approved state.** Revisions preserve their source evidence and provenance. Use a clearly labeled synthetic example if no real reviewed revision has been created. |
| 5 | Rendered system diagram from workflow-and-system-diagrams.md | **Local services, clear boundaries.** The browser connects to a camera edge and an independent image-history API; a Linux worker performs vision processing. |
| 6 | Actual camera-rig viewer or projector screen | **Explore the space in 3D.** The independent viewer and projector tools sit alongside image history. Label a simulated scene or unconfigured PointDiT view accurately. |

Do not caption a source photograph as a reconstruction. Do not imply the camera-rig
view is the approved semantic revision or that its poses prove a fused/aligned cloud.
Replace any private host paths, operator credentials and identifying imagery before
recording. Keep visible provenance badges in the frame.

## Three-minute narrated demo

This is a suggested edit plan, not an event-mandated video duration. Check the event's
actual video rules. Precompute inference if needed and identify any time cut honestly.

### 0:00–0:20 — problem and hook

**Show:** a room/workbench you have permission to film, then the app.

**Say:** “New worlds can begin in a familiar room. Git lets us inspect a software
change before accepting it; we wanted that habit for physical spaces. SpaceGit
records camera evidence, proposes what changed, and lets a person decide what
belongs in the room's approved history.”

### 0:20–0:45 — capture

**Show:** create/select a saved space and the four-file input, or an actual complete
4/4 rig session. Identify the overhead role.

**Say:** “Each space has four fixed camera roles: three side views and an overhead
view. We can upload photos or import saved camera frames. The originals stay
unchanged, with hashes and timestamps attached.”

### 0:45–1:15 — real processing

**Show:** a completed real-model run, source images, model/run provenance and one
proposed-change card. If using the recorded smoke, call it an example-photo run.

**Say:** “YOLOE supplies object detections and masks, and DINOv2 supplies appearance
features for matching within each view. This run used real pretrained models. The
69 proposals in our example show the pipeline executing; they are not 69 verified
facts or an accuracy score.”

### 1:15–1:55 — human review and commit

**Show:** a crop and run overlay; a decision reason; Accept/Reject/Needs review;
Include in revision; message and explicit commit. Use a clearly labeled fixture
or a team-reviewed real example. Do not bulk-approve the existing smoke by default.

**Say:** “The model proposes; we review. Ambiguous matches stay uncertain. Accepting
doesn't commit automatically: we choose accepted changes and save a revision with
its evidence and decision history.”

### 1:55–2:20 — history

**Show:** an actual revision, its parent, a comparison and accepted track history.

**Say:** “Approved history is a linear sequence for each space. We can inspect a
revision and see which capture supplied its evidence. A rejected newer observation
doesn't erase an older approved state.”

### 2:20–2:45 — 3D and projection

**Show:** an actual local PLY/model or the labeled simulation. If PointDiT is actually
configured and demonstrated, show its completed per-view output in Camera rig.
Show the projector window on a second display if available.

**Say:** “The 3D and projector workspace runs alongside image history. Our frontend
also includes a separate WSL PointDiT workflow for per-view clouds. Connecting
approved masks to matching point maps is the next integration step.”

### 2:45–3:00 — close

**Show:** the review screen and project name; add the repository URL in the edit.

**Say:** “SpaceGit brings capture, evidence and explicit approval into a space's
history. We are building toward a reviewable connection between what a camera sees,
what a person approves and what a 3D view can explain.”

## Short presentation script — approximately 45 seconds

“We're ZygomorphicMereOtter from Durham University. SpaceGit is version control for physical spaces. We capture three side views and
an overhead view, preserve the original images, and use pretrained YOLOE and DINOv2
to propose camera-local object changes. A person reviews the evidence, accepts or
rejects proposals, and explicitly commits selected changes into an approved history.
Alongside that, our frontend supports metric layout branches, 3D viewing and
projector output. It also includes a separate WSL PointDiT integration for per-view
clouds. Our real image-history smoke produced 69 proposals, left for human review.
Next is linking approved changes to dense point maps without losing their source
evidence. The goal is a room history you can inspect and trust.”

## Judge questions — suggested answers

**Is this Git itself storing every camera image?**

No. Git is the interaction analogy. Image history uses PostgreSQL for records and
private object storage for originals and derivatives. The independent layout
workflow has its own commit/branch model in SQLite.

**What exactly is AI doing?**

YOLOE supplies object boxes, labels and masks. DINOv2 supplies appearance embeddings.
The pipeline associates observations within a camera and proposes changes. Humans
decide what becomes approved history. The separate PointDiT integration supports
image-to-3D generation when its WSL runtime is configured.

**Does the same chair get one identity across all cameras?**

No automatic cross-camera identity is claimed. Tracks are scoped to a saved space
and camera. That preserves ambiguity instead of inventing a physical association.

**Can it tell how far something moved in metres?**

The image-history changes are image-space observations. Metric layouts belong to
the separate measured/calibrated workflow; they are not inferred by this pipeline.

**Are the point clouds already linked to approved changes?**

No. The pulled frontend has a separate WSL generation/viewer flow. Source-aligned
dense point maps and correspondence sidecars are needed for the planned backend
highlight integration. An unordered PLY alone is insufficient.

**What was actually tested?**

The recorded gates include 94 backend offline tests, 27 Linux service tests, nine
Node tests and browser contract checks. After the frontend merge, all 36 edge tests
passed. A real YOLOE/DINOv2 browser smoke processed four example photos and produced
69 observations/proposals; later inspection verified crops, overlays and the original
RLE download hash. These are execution/contract checks, not a model-quality benchmark
or a verified physical projector/WSL PointDiT demonstration.

**What happens when the models are wrong or processing fails?**

Evidence stays available for review. Failed runs retain durable status and can be
retried after fixing the cause. Rejected proposals do not advance approved history;
stale baselines must be reprocessed before committing. Real mode does not silently
switch to synthetic inference.

## Before publishing

Use an accessible video-host link supported by Devpost and allowed by the event.
Verify playback while signed out. Complete the team/table/prize fields in the
submission document, confirm collaborators and third-party credits, and check the
current event's submission and video rules. No public upload is performed here.

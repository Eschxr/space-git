# SpaceGit

**Version control for physical spaces.** Capture four camera views, review
AI-proposed changes, and build an approved image history alongside 3D viewing
and projection tools.

Built by **ZygomorphicMereOtter**, Durham University, for **DurHack 2026 —
Marshall Wace Challenge 1: New Worlds**. We explore new ways to understand a
familiar space: what it looked like, what changed, and which changes a person
chooses to approve.

## What you can do

- Create saved spaces and upload four images or import a complete live rig session.
- Run pretrained YOLOE segmentation and DINOv2 appearance matching to propose
  camera-local changes, keeping ambiguous matches visible for review.
- Inspect source images, object crops and run overlays; download original mask
  RLE JSON; record Accept, Reject or Needs review with an audit trail.
- Explicitly select accepted proposals and commit immutable approved revisions.
  Compare revisions and inspect an object's accepted history and source provenance.
- Use the independent metric layout branches, 3D/model viewers and projector tools.
- With the external WSL environment configured, generate per-view PointDiT PLYs
  through the camera edge and inspect them in the Camera rig viewer.

```mermaid
flowchart LR
    A["Four fixed camera views"] --> B["Immutable capture"]
    B --> C["YOLOE + DINOv2"]
    C --> D["Camera-local tracks and proposed changes"]
    D --> E["Human review"]
    E --> F["Commit selected accepted changes"]
    F --> G["Approved image history"]
```

`cam_01..cam_03` are side views; `cam_04` is overhead. Keep the cameras fixed
between captures. Accepting a proposal and committing it are separate actions.
Tracks stay scoped to a space and camera; image changes do not imply metric
movement or automatic physical identity across views.

## Run the integrated app

Use Git, Docker Desktop/Compose, Node.js 24 and pnpm 11.25.0. Camera control also
needs a separate Python 3.12 environment. The Docker API/vision worker use Python
3.11; the pinned durable RQ worker requires Linux.

| Component | Local address |
| --- | --- |
| Frontend | http://127.0.0.1:3101 |
| Image history | http://127.0.0.1:3101/image-history |
| Capture / 3D / Project | http://127.0.0.1:3101/world |
| Scene Tracker backend API | http://127.0.0.1:8001 |
| Camera edge | http://127.0.0.1:8002 |
| PostgreSQL / Redis | Loopback ports 5432 / 6379 |
| Silo objects / console | Loopback ports 9000 / 9001 |

These web/API/edge ports keep this checkout separate from the older local
SpaceGit-MVP services on 3000/3100/8000.

From the repository root in PowerShell, with Docker Desktop running:

```powershell
# First setup only: retain any existing operator configuration.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose --env-file .env -f infra/compose.yaml --profile application up -d --build

cd frontend
pnpm install --frozen-lockfile
if (-not (Test-Path apps/web/.env.local)) {
    Copy-Item apps/web/.env.local.example apps/web/.env.local
}
pnpm dev --port 3101
```

This starts the image-file workflow without requiring cameras. The Compose profile
runs additive migrations, API, worker, PostgreSQL, Redis and private Silo storage.
The first vision image build can take several minutes and multiple gigabytes.

The example `.env` selects **fake fixture extraction**. For real inference, follow
[model setup](docs/model-setup.md), configure the verified local YOLOE/DINOv2 assets
and hashes, and select `VISION_PROVIDER=real` before starting the containers.
Model weights are not downloaded by the image build or tests. Real mode fails
explicitly if its assets are unavailable. To verify an already configured runtime:

```powershell
docker compose --env-file .env -f infra/compose.yaml exec api scene-tracker model-readiness --runtime
```

Use [the full startup and operator guide](docs/frontend-integration.md) for camera
environment installation, Linux instructions, model mounts and troubleshooting.
After installing the camera dependencies, the Windows launcher is run from
`frontend/` instead of the standalone `pnpm dev` command:

```powershell
.\scripts\start.ps1 -Mode live -Port 3101 -EdgePort 8002
```

The merged Windows launcher also enables the WSL PointDiT workflow, using its
configured Ubuntu user `wilson` and fixed image/output paths. Capture export
replaces the latest export folder; saved edge session JPEGs remain retained.
Review the [frontend README](frontend/README.md) before using that generation path.
Stop existing instances on the selected ports before launching replacements.

## Use Image history

1. Open **Image history** and choose or create a saved space.
2. Upload three side views and one overhead view, or import a saved complete 4/4
   live camera session. Original bytes, hashes and capture metadata are retained.
3. Click **Run inference** and inspect the run's provider, status and provenance.
4. Review each proposal using source/crop/overlay evidence. Individual masks are
   offered as COCO compressed RLE JSON downloads, not image previews.
5. Record decisions, check **Include in revision** on accepted changes, enter a
   message and click **Commit selected changes**.
6. Open an approved revision to compare states or inspect accepted track history.

Rejected and unselected observations do not automatically replace approved state.
Stale baselines require reprocessing; inspection-only runs cannot be committed.
Use **Refresh evidence** to renew expired signed links. After an upload timeout,
refresh the capture list before repeating the upload.

## Documentation and project writing

| Document | Contents |
| --- | --- |
| [Workflow and system diagrams](docs/workflow-and-system-diagrams.md) | Deployment, image review pipeline, reconstruction and projection boundaries |
| [Integration guide](docs/frontend-integration.md) | Service startup, settings, operator steps and endpoint mapping |
| [Devpost submission](docs/devpost-submission.md) | Project story, pitch, technology tags, team details and organizer answers |
| [Media and demo copy](docs/devpost-media-and-demo.md) | Gallery captions, narration, short presentation and judge Q&A |
| [Prize assessment](docs/devpost-prize-assessment.md) | New Worlds positioning and conditional DEV Writing Challenge entry |
| [DEV article draft](docs/dev-article-draft.md) | Unpublished technical article for team review |
| [Model setup](docs/model-setup.md) | Local weights, hashes and pinned source requirements |
| [API reference](docs/api.md) | Capture, processing, review, revision and evidence contracts |
| [Implementation record](docs/implementation-status.md) | Completed work, validation results and limitations |

## Validation and scope

Scene Tracker backend Phases 6–8 and its frontend image-history connection are
implemented. Recorded validation includes 94 backend offline tests, 27 Linux
service tests, nine client tests and browser checks. Following the frontend merge,
all 36 edge tests passed. A real YOLOE/DINOv2 browser smoke processed four example
photos into 69 observations and 69 proposals, left pending human review.

That smoke verifies execution, not model accuracy or controlled fixed-rig tracking.
Synthetic fixtures and the simulated office remain explicitly separate. The WSL
PointDiT wrapper/viewer is implemented independently; the recorded tests do not
certify its real generation quality or physical projector calibration.

Keep `.env` private and use operator-specific credentials. Services bind to
loopback; Scene Tracker authentication remains outside the local MVP. Silo objects
are private, with short-lived signed browser URLs. Data lives in persistent named
volumes; use `docker compose --env-file .env -f infra/compose.yaml stop` to stop
services while retaining it. [Storage decision](docs/adr/0002-silo-object-storage.md).

## One-command fake two-capture smoke

With the three services already running and backend CPU dependencies installed:

```bash
# From the repository root; output directory MUST be new:
scripts/smoke-fake.sh /tmp/scene-tracker-fake-demo
```

The script runs HTTP ingestion, four-view fake extraction, tracks, move/new proposals,
review/commit, revision diff, before/after manifests and synthetic highlighted PLY
export. It also checks reprocessing and worker failure preserve history/originals.
It uses isolated test SQL schemas and S3 buckets, cleans those afterward, and does not
start/stop containers or alter the development schema. Override `TEST_DATABASE_URL`,
`TEST_S3_ENDPOINT`, `TEST_S3_ACCESS_KEY`, `TEST_S3_SECRET_KEY`, `TEST_REDIS_URL` if your
local credentials/ports differ from `.env.example`.

Exports include `summary.html`, `inspection.zip`, `diff.json`, `summary.json`, eight
before/after manifests and per-camera highlighted/source-colored synthetic PLYs with
mapping sidecars. Exported signed URLs expire and test buckets are cleaned; the local
report/bundle/PLY evidence remains inspectable. **Synthetic XYZ is a flat grid, not
PointDiT reconstruction. Fake outputs validate contracts, not pretrained quality.**

For a persistent manual fake API walkthrough:

```bash
cd backend
uv run --no-group vision scene-tracker synthetic-capture --output ../local-data/capture-a
uv run --no-group vision scene-tracker synthetic-capture --output ../local-data/capture-b --moved
```

Upload those files and follow [API examples](docs/api.md). Explicit PNG fixture metadata
supplies boxes and appearance seeds; pixels do not drive fake inference. Images without
metadata produce zero fake detections and a warning.

## Tests

```bash
cd backend
uv sync --locked --no-group vision
uv run --no-group vision ruff check . ../scripts
uv run --no-group vision ruff format --check . ../scripts
uv run --no-group vision pytest -q
```

Service tests require the existing containers and use isolated schemas/buckets/queues.
From the repository root, using example credentials:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://scene_tracker:local-dev-change-me@localhost:5432/scene_tracker'
export TEST_S3_ENDPOINT=localhost:9000
export TEST_S3_ACCESS_KEY=scene_tracker
export TEST_S3_SECRET_KEY=local-dev-change-me
export TEST_REDIS_URL=redis://localhost:6379/0
uv run --project backend --no-group vision pytest -q -m integration backend/tests/integration
```

Ordinary tests never install/download model weights. Service tests are excluded by
default and fail explicitly when their services/configuration are absent. An optional
manual real smoke and runtime limitations are documented in model setup.

## Architecture and reconstruction boundary

[Architecture](docs/architecture.md), [matching/review rules](docs/matching-and-diffs.md),
[data model](docs/data-model.md), [highlight contract](docs/highlights.md),
[retired pipeline](docs/legacy-vision-pipeline.md).

`reconstruction/` remains an independent Python **3.12** uv project and a future
Scene Tracker Phase 9 worker. It is a scaffold for reconstruction jobs, immutable
artifacts and source-pixel correspondence. The separate frontend WSL PointDiT
wrapper does not implement that backend contract. Its checks are independent:

```bash
cd reconstruction
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Future outputs are one PLY per view, with explicit pixel-map transforms and independent
camera coordinates. Capture/run discovery, auditable reviews, historical source images,
accepted track history and endpoint comparisons are described in the
[image-history HTTP workflow](docs/api.md#capture-workflow-and-processing-attempts).
The frontend's implemented Image history adapter consumes the typed backend
workflow/revision evidence contracts. Its metric scene/branch model and WSL camera-rig
viewer remain independent. Source-aligned point-cloud highlights, dense point maps
and immutable Scene Tracker reconstruction delivery remain Phase 9. An unordered PLY
alone cannot supply the required pixel-to-point mapping; no verified fused scene or
automatic cross-camera identity is implied.

The pinned RQ SpawnWorker uses POSIX process APIs. Run durable workers on Linux.
The Windows host supports the API and standalone CPU model smoke. The full service
suite, including the spawned worker, is validated in Linux containers.

# Scene Tracker

Scene Tracker keeps reviewable image-view history from four fixed cameras:
`cam_01..cam_03` side views and `cam_04` overhead. The backend runs **YOLOE prompt-free
segmentation → DINOv2 → same-camera tracks → proposed changes → accepted revisions**.
Original images and accepted history stay immutable. Ambiguous matches remain visible
for review; physical identity is never merged automatically across cameras.

Refactor R0–R6 replaces the old prompted pipeline. Fake/stub and real-service tests
validate the workflow; real pretrained inference remains unvalidated on this host
without operator assets/runtime. [Status](docs/refactor-status.md),
[historical implementation record](docs/implementation-status.md),
[controlling refactor plan](CODEX_YOLOE_REFACTOR_PLAN.md).

## Local development

Install Git, uv and Docker Compose. PostgreSQL, Redis and PGSTY Silo run in containers;
you do not need host PostgreSQL/Redis installations. Python workers/API run through uv.
From the root:

```bash
cp .env.example .env
uv python install 3.11 3.12
docker compose --env-file .env -f infra/compose.yaml up -d
cd backend
uv sync --locked --no-group vision
uv run --env-file ../.env --no-group vision alembic upgrade head
uv run --env-file ../.env --no-group vision uvicorn scene_tracker.api.main:app --reload
# Separate terminal, from backend/:
uv run --env-file ../.env --no-group vision scene-tracker worker vision
# Add --burst to drain queued work and exit.
```

The example configuration uses fake extraction. `GET http://127.0.0.1:8000/health/live`
checks liveness only. Infrastructure and API bind to loopback; authentication remains
outside the local MVP. Change example credentials before use and keep `.env` private.
Migrations are additive; do not reset the database. Silo bootstrap creates a private
bucket without deleting data; named volumes survive `docker compose down`.
[Storage decision and pinned image](docs/adr/0002-silo-object-storage.md).

For real inference, follow [model-setup.md](docs/model-setup.md). It specifies the
local `yoloe-11s-seg-pf.pt` checkpoint, hashes, pinned DINOv2 source and
`uv sync --locked --group vision`. No prompts/text encoder or old SAM setup is needed.
API imports load no model libraries. Missing real assets fail explicitly.
[Third-party notices](THIRD_PARTY_NOTICES.md) cover Ultralytics/YOLOE AGPL-3.0 or
commercial licensing and DINOv2 terms; public hosting alone does not settle compliance.

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

`reconstruction/` remains an independent Python **3.12** uv project and a future P9
worker. It is currently a scaffold; PointDiT and separately gated DINOv3 assets are not
installed or integrated. Its checks are independent:

```bash
cd reconstruction
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Future outputs are one PLY per view, with explicit pixel-map transforms and no claim
of cross-view alignment. No frontend, camera calibration/registration, OpenUSD,
metric movement or fused 3D is implemented. To stop existing infrastructure while
retaining volumes: `docker compose --env-file .env -f infra/compose.yaml stop`.

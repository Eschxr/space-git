# space-git

Scene Tracker builds a reviewable semantic history from four fixed-role images:
`cam_01`, `cam_02`, `cam_03` (side views) and `cam_04` (overhead).
Original images remain immutable evidence. Same-camera tracking precedes reviewable
cross-view associations; ambiguous identities remain unresolved for human review.

Phase 1 adds domain schemas, a PostgreSQL migration, storage adapters and a four-image
ingestion helper. Its MinIO integration gate is blocked by registry access. HTTP
capture ingestion, inference, review and reconstruction remain later-phase work.
See [the plan](CODEX_IMPLEMENTATION_PLAN.md) and [implementation status](docs/implementation-status.md).

## Development

Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Docker
with Compose. CPU development requires no GPU or model weights.
From the repository root:

```bash
cp .env.example .env
uv python install 3.11 3.12
docker compose --env-file .env -f infra/compose.yaml config
docker compose --env-file .env -f infra/compose.yaml up -d
cd backend
uv sync --no-group vision
uv run --no-group vision ruff check .
uv run --no-group vision ruff format --check .
uv run --no-group vision pytest
uv run --no-group vision uvicorn scene_tracker.api.main:app --reload --env-file ../.env
```

`GET http://127.0.0.1:8000/health/live` returns `{"status":"ok"}`.
It checks process liveness only. No dependency or model readiness is claimed.
Settings load environment variables or `.env` in the current directory. The API
command above loads the root `.env`. Local credentials are examples; edit `.env`
before use and never commit it. Infrastructure ports bind only to loopback.
MinIO bootstrap creates the configured private bucket without deleting existing data.
Named volumes retain data across `docker compose down`.

The projects have independent Python environments and lockfiles, with no root uv workspace:

```bash
cd reconstruction
uv sync
uv run ruff check .
uv run pytest
uv run reconstruction-worker --help
```

The CLI entry points exist, but worker execution currently exits with an explicit
not-implemented error. Vision job orchestration arrives in Phase 2 and PointDiT
in Phase 9. Their eventual commands are:

```bash
cd backend
uv run --no-group vision scene-tracker worker vision
# In a separate terminal/environment:
cd reconstruction
uv run reconstruction-worker
```

Pretrained weights and official model dependencies are separate operator setup;
ordinary tests never fetch weights. The `vision` group is currently empty pending
Phase 4. No real inference or model-quality validation has occurred.

There is no frontend, camera control/calibration, registration, OpenUSD or 3D fusion.
Movement uses pixels or normalized image coordinates. Future PointDiT outputs are
per-camera PLY, with no claim of world-space alignment. The eventual service assumes
a single local operator; authentication is deferred and public deployment unsupported.

## Phase 1 schema and storage tests

The domain schemas, migration, immutable storage adapters and ingestion helper are
implemented. HTTP capture ingestion and durable job orchestration remain Phase 2.
Pillow is a CPU dependency for image validation; it does not load ML models.

Run offline checks from `backend/`:

```bash
uv sync --no-group vision
uv run --no-group vision ruff check .
uv run --no-group vision ruff format --check .
uv run --no-group vision pytest
```

Service tests are explicitly marked `integration` and excluded from the default
suite. They require real PostgreSQL and MinIO, and fail if configuration is missing.
They create and remove only isolated test schemas and uniquely named test buckets.
From the repository root, using local example credentials:

```bash
docker compose --env-file .env.example -f infra/compose.yaml up -d postgres minio minio-init
export TEST_DATABASE_URL='postgresql+psycopg://scene_tracker:local-dev-change-me@localhost:5432/scene_tracker'
export TEST_S3_ENDPOINT='localhost:9000'
export TEST_S3_ACCESS_KEY='scene_tracker'
export TEST_S3_SECRET_KEY='local-dev-change-me'
cd backend
uv run --no-group vision pytest -m integration
```

For migrations against the development database, export `DATABASE_URL` from your
root `.env`, then run `uv run --no-group vision alembic upgrade head` in `backend/`.
The initial migration creates all planned tables; later phases implement their
application behavior. See [data model](docs/data-model.md).

At the Phase 1 checkpoint, PostgreSQL started and its integration checks passed.
MinIO image pulls failed: Docker Hub reported pull access denied, and Quay returned
401 Unauthorized for both pinned server and client images. The Compose file exposes
`MINIO_IMAGE` and `MINIO_MC_IMAGE` overrides for an operator-accessible mirror; no
third-party replacement or fake S3 service has been substituted. Until the MinIO
integration test passes, Phase 1 is blocked and later phases must not begin.
PostgreSQL was left running; stop it without deleting data using:

```bash
docker compose --env-file .env.example -f infra/compose.yaml stop postgres
```

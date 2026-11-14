# space-git

Scene Tracker builds a reviewable semantic history from four fixed-role images:
`cam_01`, `cam_02`, `cam_03` (side views) and `cam_04` (overhead).
Original images remain immutable evidence. Same-camera tracking precedes reviewable
cross-view associations; ambiguous identities remain unresolved for human review.

Phase 2 adds capture upload/list/retrieval APIs and durable Redis/RQ orchestration.
PostgreSQL, Silo and Redis integration tests pass. The worker currently validates
orchestration only; vision inference, review and reconstruction remain later phases.
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
uv run --env-file ../.env --no-group vision alembic upgrade head
uv run --env-file ../.env --no-group vision uvicorn scene_tracker.api.main:app --reload
```

`GET http://127.0.0.1:8000/health/live` returns `{"status":"ok"}`.
It checks process liveness only. No dependency or model readiness is claimed.
Settings load environment variables or `.env` in the current directory. The API
command above loads the root `.env`. Local credentials are examples; edit `.env`
before use and never commit it. Infrastructure ports bind only to loopback.
Silo bootstrap creates the configured private bucket without deleting existing data.
Named volumes retain data across `docker compose down`.

The projects have independent Python environments and lockfiles, with no root uv workspace:

```bash
cd reconstruction
uv sync
uv run ruff check .
uv run pytest
uv run reconstruction-worker --help
```

Start the vision orchestration worker in a separate terminal from `backend/`:

```bash
uv run --env-file ../.env --no-group vision scene-tracker worker vision
# Process queued work and exit:
uv run --env-file ../.env --no-group vision scene-tracker worker vision --burst
```

The worker uses RQ SpawnWorker and JSON serialization, never initializes GPU models
in its parent, and reads IDs/configuration from PostgreSQL. Phase 2 supports the
`skeleton` preset with `VISION_PROVIDER=fake`: success means orchestration completed,
with manifest `inference_performed: false`. Real mode returns `model_unavailable`;
no fake inference is substituted. Reconstruction CLI execution remains a placeholder
until Phase 9. See [API examples and retry behavior](docs/api.md).

Pretrained weights and official model dependencies are separate operator setup;
ordinary tests never fetch weights. The `vision` group is currently empty pending
Phase 4. No real inference or model-quality validation has occurred.

There is no frontend, camera control/calibration, registration, OpenUSD or 3D fusion.
Movement uses pixels or normalized image coordinates. Future PointDiT outputs are
per-camera PLY, with no claim of world-space alignment. The eventual service assumes
a single local operator; authentication is deferred and public deployment unsupported.

## Phase 1 schema and storage tests

The domain schemas, migration, immutable storage adapters and ingestion helper are
implemented. Phase 2 adds HTTP ingestion and durable job orchestration.
Pillow is a CPU dependency for image validation; it does not load ML models.

Run offline checks from `backend/`:

```bash
uv sync --no-group vision
uv run --no-group vision ruff check .
uv run --no-group vision ruff format --check .
uv run --no-group vision pytest
```

Service tests are explicitly marked `integration` and excluded from the default
suite. They require real PostgreSQL, Silo (S3-compatible storage) and Redis, and fail if
configuration is missing.
They create and remove only isolated test schemas and uniquely named test buckets.
From the repository root, using local example credentials:

```bash
docker compose --env-file .env.example -f infra/compose.yaml up -d postgres silo silo-init redis
export TEST_DATABASE_URL='postgresql+psycopg://scene_tracker:local-dev-change-me@localhost:5432/scene_tracker'
export TEST_S3_ENDPOINT='localhost:9000'
export TEST_S3_ACCESS_KEY='scene_tracker'
export TEST_S3_SECRET_KEY='local-dev-change-me'
export TEST_REDIS_URL='redis://localhost:6379/0'
cd backend
uv run --no-group vision pytest -m integration
```

For migrations against the development database, export `DATABASE_URL` from your
root `.env`, then run `uv run --no-group vision alembic upgrade head` in `backend/`.
The initial migration creates all planned tables; later phases implement their
application behavior. See [data model](docs/data-model.md).

Local object storage uses [PGSTY Silo](https://github.com/pgsty/silo), a maintained
MinIO fork, following the operator-approved replacement of unavailable MinIO images.
Compose pins release `RELEASE.2026-11-12T00-00-00Z` by digest. The same image supplies
the server and bundled `mcli` bucket bootstrap; no separate MinIO client image is
needed. `SILO_IMAGE` can override the image for an accessible mirror. The existing
Python MinIO SDK remains the S3 client; no new Python dependencies were required.
See [the storage decision](docs/adr/0002-silo-object-storage.md).

S3 and console ports remain `127.0.0.1:9000` and `127.0.0.1:9001`. Credentials still
use `S3_ACCESS_KEY` / `S3_SECRET_KEY`; the server accepts the compatible `MINIO_*`
variables supplied by Compose. The existing `minio_data` named volume is retained
for continuity. No existing data was migrated or deleted. Silo is AGPL-3.0-or-later;
its release source, license and notices are linked in the storage decision.

Phase 2 tests pass, and PostgreSQL, Silo and Redis are left running. Stop them without
deleting data using:

```bash
docker compose --env-file .env.example -f infra/compose.yaml stop postgres silo redis
```

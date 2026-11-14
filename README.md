# space-git

Scene Tracker builds a reviewable semantic history from four fixed-role images:
`cam_01`, `cam_02`, `cam_03` (side views) and `cam_04` (overhead).
Original images remain immutable evidence. Same-camera tracking precedes reviewable
cross-view associations; ambiguous identities remain unresolved for human review.

Phase 4 adds real Grounding DINO → SAM 2.1 → DINOv2 adapters, pinned source/hash
preflight and manual model smoke commands. CPU tests and PostgreSQL/Silo/Redis service
checks pass. Real inference remains unvalidated here because operator model assets
and the optional ML runtime are not installed. Fake processing remains the default.
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

Start the fake vision worker in a separate terminal from `backend/`:

```bash
uv run --env-file ../.env --no-group vision scene-tracker worker vision
# Process queued work and exit:
uv run --env-file ../.env --no-group vision scene-tracker worker vision --burst
```

The worker uses RQ SpawnWorker and JSON serialization, never initializes GPU models
in its parent, and reads IDs/configuration from PostgreSQL. Phase 3 supports the
`fake-fixture` preset (`skeleton` is an alias) with `VISION_PROVIDER=fake`. It uses
explicit fixture metadata, with manifest `inference_performed: false` and
`scope: synthetic_fixture_pipeline`. Real mode verifies local assets before enqueueing and loads models only in the
worker; missing assets return `model_unavailable` with no fake fallback. See
[real-model setup](docs/model-setup.md) for `uv sync --group vision` and real worker commands. Reconstruction CLI execution remains a placeholder
until Phase 9. See [API examples and retry behavior](docs/api.md).

Pretrained weights and official model dependencies are separate operator setup;
ordinary tests never fetch weights. The optional `vision` group pins Torch/TorchVision and real-model support packages.
The dev group includes CPU NumPy/pycocotools for offline stub/fake tests, so
`--no-group vision` never installs the heavyweight real runtime. Official source
checkouts and weights are separate operator setup. No real inference or model-quality
validation has occurred in this workspace.

There is no frontend, camera control/calibration, registration, OpenUSD or 3D fusion.
Movement uses pixels or normalized image coordinates. Future PointDiT outputs are
per-camera PLY, with no claim of world-space alignment. The eventual service assumes
a single local operator; authentication is deferred and public deployment unsupported.

## Backend and service tests

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

Phase 4 tests pass, and PostgreSQL, Silo and Redis are left running. Stop them without
deleting data using:

```bash
docker compose --env-file .env.example -f infra/compose.yaml stop postgres silo redis
```


## Synthetic inspection workflow

Generate four labeled PNG fixtures from `backend/` (the output directory must not
already contain the images):

```bash
uv run --no-group vision scene-tracker synthetic-capture --output ../local-data/capture-a
uv run --no-group vision scene-tracker synthetic-capture --output ../local-data/capture-b --moved
# A no-object fixture is also supported with --empty.
```

Each PNG contains validated `scene_tracker_fixture` metadata. The fake detector
reads those boxes, the fake segmenter makes rectangle masks, and the fake embedder
normalizes deterministic seed hashes into eight-dimensional vectors. Image pixels
do not drive ML detection. Images without fixture metadata produce zero detections
with a warning, rather than invented scene results.

Use the [API examples](docs/api.md) to upload `cam_01.png` through `cam_04.png`,
POST `/captures/{id}/process` with `{"preset":"fake-fixture"}`, and start the worker.
GET `/processing-runs/{id}/detections` returns per-frame detections;
GET `/processing-runs/{id}/debug` returns the manifest and short-lived artifact URLs.
Download `kind: report` for a standalone HTML report or `kind: inspection_bundle`
for a ZIP containing all stored derivatives, overlays, crop sheets and JSON diagnostics.
The static report prominently identifies cam_04 as overhead. Tracking/association/change
JSON files explicitly state `implemented: false` until their planned phases.

To export a reviewable smoke result while running the service test suite, set
`SCENE_TRACKER_SMOKE_OUTPUT=/tmp/scene-tracker-phase3-smoke` alongside the TEST_* variables
above before running `uv run --no-group vision pytest -m integration`. The export holds
`summary.html`, `inspection.zip` and `run.json`. Temporary service schemas/buckets are
still cleaned by tests. These fake tests verify code contracts, not pretrained model quality.


## Optional real vision (Phase 4)

Follow [model setup](docs/model-setup.md) to install pinned sources/runtime and supply
verified local checkpoints plus BERT assets. No command here downloads weights.
From `backend/`:

```bash
uv run --env-file ../.env --no-group vision scene-tracker model-readiness
# After operator setup (loads real models/device but does not infer):
uv run --env-file ../.env --group vision scene-tracker model-readiness --runtime
# Manual-only, four supplied camera-role images; output directory must be new:
uv run --env-file ../.env --group vision scene-tracker model-smoke \
  --input /absolute/path/to/four-images --output /absolute/path/to/new-smoke-output
```

Set `VISION_PROVIDER=real` for the API to select the real pipeline; provider/configuration
are snapshotted server-side, not chosen through client-provided paths. The regular worker
uses `uv run --env-file ../.env --group vision scene-tracker worker vision`. Configure
per-environment detector prompts when creating the environment, e.g.
`{"name":"office","prompts":["chair","table","computer monitor","box"]}`.
The prompt catalogue cannot ensure extraction of unknown types. Source/hash preflight
is CPU-only; it does not certify a remote worker runtime or visual/semantic quality.

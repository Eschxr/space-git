# space-git

Scene Tracker builds a reviewable semantic history from four fixed-role images:
`cam_01`, `cam_02`, `cam_03` (side views) and `cam_04` (overhead).
Original images remain immutable evidence. Same-camera tracking precedes reviewable
cross-view associations; ambiguous identities remain unresolved for human review.

Phase 0 supplies project scaffolding and liveness only. Capture ingestion, model
inference, persistence, review and reconstruction are implemented in later phases.
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

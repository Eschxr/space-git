#!/usr/bin/env bash
# Uses existing local services; temporary SQL schemas/buckets are cleaned by pytest.
set -euo pipefail
cd "$(dirname "$0")/.."
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://scene_tracker:local-dev-change-me@localhost:5432/scene_tracker}"
export TEST_S3_ENDPOINT="${TEST_S3_ENDPOINT:-localhost:9000}"
export TEST_S3_ACCESS_KEY="${TEST_S3_ACCESS_KEY:-scene_tracker}"
export TEST_S3_SECRET_KEY="${TEST_S3_SECRET_KEY:-local-dev-change-me}"
export TEST_REDIS_URL="${TEST_REDIS_URL:-redis://localhost:6379/0}"
export SCENE_TRACKER_E2E_OUTPUT="${1:?Usage: scripts/smoke-fake.sh /absolute/path/to/new-output-directory}"
exec uv run --project backend --locked --no-group vision pytest -q -m integration \
  backend/tests/integration/test_capture_api.py::test_full_fake_refactor_e2e

import io
import os
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from minio import Minio
from PIL import Image
from sqlalchemy import func, select

from scene_tracker.api.dependencies import Services
from scene_tracker.api.main import create_app
from scene_tracker.application.process import ProcessingService
from scene_tracker.core.settings import Settings
from scene_tracker.infrastructure.db.models import jobs, processing_runs
from scene_tracker.infrastructure.db.repositories import Repository
from scene_tracker.infrastructure.queue.inline import InlineDispatcher
from scene_tracker.infrastructure.storage.base import Blob
from scene_tracker.infrastructure.storage.s3 import S3Store
from scene_tracker.workers.jobs import execute_vision

pytestmark = pytest.mark.integration


@pytest.fixture
def api(database):
    engine, config = database
    command.upgrade(config, "head")
    client = Minio(
        os.environ["TEST_S3_ENDPOINT"],
        access_key=os.environ["TEST_S3_ACCESS_KEY"],
        secret_key=os.environ["TEST_S3_SECRET_KEY"],
        secure=False,
    )
    bucket = "test-" + uuid4().hex
    client.make_bucket(bucket)
    settings = Settings(_env_file=None, vision_provider="fake")
    services = Services(
        Repository(engine), lambda env: S3Store(client, bucket, env), InlineDispatcher(), settings
    )
    try:
        with TestClient(create_app(settings, services)) as test_client:
            yield SimpleNamespace(client=test_client, services=services, engine=engine)
    finally:
        for obj in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, obj.object_name)
        client.remove_bucket(bucket)


def files():
    stream = io.BytesIO()
    Image.new("RGB", (12, 8), "red").save(stream, format="PNG")
    return [
        (f"cam_{i:02}", (f"cam_{i:02}.png", stream.getvalue(), "image/png")) for i in range(1, 5)
    ]


def capture(api):
    env = api.client.post("/api/v1/environments", json={"name": "room"})
    assert env.status_code == 201
    response = api.client.post(f"/api/v1/environments/{env.json()['id']}/captures", files=files())
    assert response.status_code == 201, response.text
    return response.json()


def test_four_frame_ingestion_retrieval_and_failed_state(api):
    result = capture(api)
    assert result["status"] == "ready"
    assert len(result["frames"]) == 4
    assert result["frames"][3]["role"] == "overhead"
    retrieved = api.client.get(f"/api/v1/captures/{result['id']}")
    assert retrieved.json() == result
    for frame in result["frames"]:
        data = files()[0][1][1]
        blob = Blob(frame["storage_key"], frame["sha256"], frame["content_type"], len(data))
        assert api.services.store_factory(UUID(result["environment_id"])).get(blob) == data
    bad = files()
    bad[-1] = ("cam_04", ("cam_04.png", b"corrupt", "image/png"))
    response = api.client.post(
        f"/api/v1/environments/{result['environment_id']}/captures", files=bad
    )
    assert response.status_code == 422
    failed = api.client.get(f"/api/v1/captures/{response.json()['error']['capture_id']}").json()
    assert failed["status"] == "failed"
    assert failed["frames"] == []
    page = api.client.get(f"/api/v1/environments/{result['environment_id']}/captures?limit=1")
    assert len(page.json()["items"]) == 1
    assert api.client.get(f"/api/v1/captures/{uuid4()}").status_code == 404


def test_idempotent_processing_failure_and_new_run_retry(api):
    result = capture(api)
    path = f"/api/v1/captures/{result['id']}/process"
    first = api.client.post(path, json={}).json()
    again = api.client.post(path, json={}).json()
    assert first["id"] == again["id"]
    assert first["status"] == "queued"
    assert len(api.services.dispatcher.pending) == 1

    def fail(run, capture):
        assert api.services.repository.run(run["id"])["status"] == "running"
        raise RuntimeError("injected worker failure")

    with pytest.raises(RuntimeError, match="injected"):
        api.services.dispatcher.drain(
            lambda job, run: execute_vision(
                api.services.repository, UUID(job), UUID(run), stage=fail
            )
        )
    failed = api.client.get(f"/api/v1/processing-runs/{first['id']}").json()
    assert failed["status"] == "failed"
    assert "injected worker failure" in failed["error"]
    assert api.client.post(path, json={}).json()["id"] == first["id"]
    retry = api.client.post(path, json={"retry": True}).json()
    assert retry["id"] != first["id"]
    assert retry["job"]["id"] == first["job"]["id"]
    assert retry["job"]["attempt"] == 2
    # Old delivery must not claim the new attempt.
    execute_vision(api.services.repository, UUID(first["job"]["id"]), UUID(first["id"]))
    assert api.services.repository.run(UUID(retry["id"]))["status"] == "queued"
    api.services.dispatcher.drain(
        lambda job, run: execute_vision(api.services.repository, UUID(job), UUID(run))
    )
    done = api.client.get(f"/api/v1/processing-runs/{retry['id']}").json()
    assert done["status"] == "succeeded"
    assert done["model_manifest"]["inference_performed"] is False
    assert api.services.repository.run(UUID(first["id"]))["status"] == "failed"
    with api.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(jobs)) == 1
        assert conn.scalar(select(func.count()).select_from(processing_runs)) == 2


def test_concurrent_schedule_and_queue_outage(api):
    result = capture(api)
    service = ProcessingService(
        api.services.repository, api.services.dispatcher, api.services.settings
    )
    with ThreadPoolExecutor(4) as pool:
        runs = list(pool.map(lambda _: service.schedule(UUID(result["id"])), range(4)))
    assert len({r["id"] for r in runs}) == 1
    assert len(api.services.dispatcher.pending) == 1

    class BrokenQueue:
        def enqueue_vision(self, *args):
            raise ConnectionError("redis unavailable")

    other = capture(api)
    with pytest.raises(Exception) as exc:
        ProcessingService(api.services.repository, BrokenQueue(), api.services.settings).schedule(
            UUID(other["id"])
        )
    assert exc.value.code == "queue_unavailable"
    failed = api.services.repository.run(UUID(exc.value.details["processing_run_id"]))
    assert failed["status"] == "failed"


def test_storage_failure_and_real_mode_do_not_fallback(api):
    result = capture(api)
    api.services.settings.vision_provider = "real"
    response = api.client.post(f"/api/v1/captures/{result['id']}/process", json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"

    def broken_store(env):
        raise OSError("S3 offline")

    api.services.store_factory = broken_store
    response = api.client.post(
        f"/api/v1/environments/{result['environment_id']}/captures", files=files()
    )
    assert response.status_code == 503
    failed = api.services.repository.capture(UUID(response.json()["error"]["capture_id"]))
    assert failed["status"] == "failed"
    assert not failed["frames"]


def test_frame_timestamps_and_per_image_limits(api):
    result = capture(api)
    path = f"/api/v1/environments/{result['environment_id']}/captures"
    response = api.client.post(
        path,
        files=files(),
        data={"captured_at": "2026-11-14T12:00:00Z", "cam_04_captured_at": "2026-11-14T12:00:05Z"},
    )
    assert response.status_code == 201
    assert response.json()["warnings"]
    assert response.json()["frames"][-1]["captured_at"] == "2026-11-14T12:00:05Z"
    api.services.settings.max_image_bytes = 1
    response = api.client.post(path, files=files())
    assert response.status_code == 422
    failed_id = response.json()["error"]["capture_id"]
    assert api.client.get(f"/api/v1/captures/{failed_id}").json()["status"] == "failed"
    assert api.client.post(f"/api/v1/captures/{failed_id}/process", json={}).status_code == 409

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from minio import Minio
from rq.job import Job
from rq.serializers import JSONSerializer
from sqlalchemy import update

from scene_tracker.application.process import ProcessingService
from scene_tracker.core.settings import Settings
from scene_tracker.domain.enums import CameraID
from scene_tracker.infrastructure.db.models import captures, environments, frames
from scene_tracker.infrastructure.db.repositories import Repository
from scene_tracker.infrastructure.queue.rq import RQDispatcher
from scene_tracker.infrastructure.storage.base import checksum
from scene_tracker.infrastructure.storage.s3 import S3Store
from scene_tracker.vision.fixtures import synthetic_image

pytestmark = pytest.mark.integration


def test_spawnworker_json_failure_retry_and_durable_status(database, monkeypatch):
    engine, config = database
    command.upgrade(config, "head")
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not redis_url:
        pytest.fail("Set TEST_REDIS_URL to the Compose Redis URL")
    monkeypatch.setenv("REDIS_URL", redis_url)
    queue_name = "test-vision-" + uuid4().hex
    dispatcher = RQDispatcher(redis_url, queue_name)
    bucket = "test-" + uuid4().hex
    client = Minio(
        os.environ["TEST_S3_ENDPOINT"],
        access_key=os.environ["TEST_S3_ACCESS_KEY"],
        secret_key=os.environ["TEST_S3_SECRET_KEY"],
        secure=False,
    )
    client.make_bucket(bucket)
    for setting in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        monkeypatch.setenv(setting, os.environ["TEST_" + setting])
    monkeypatch.setenv("S3_BUCKET", bucket)
    repository = Repository(engine)
    env, capture_id = uuid4(), uuid4()
    store = S3Store(client, bucket, env)
    with engine.begin() as conn:
        conn.execute(environments.insert().values(id=env, name="worker test"))
        conn.execute(
            captures.insert().values(
                id=capture_id, environment_id=env, captured_at=datetime.now(UTC), status="uploading"
            )
        )
        for i in range(1, 5):
            camera = CameraID(f"cam_{i:02}")
            raw = synthetic_image(camera)
            key = f"originals/{env}/{capture_id}/{camera}/{checksum(raw)}.png"
            store.put(key, raw, "image/png")
            conn.execute(
                frames.insert().values(
                    environment_id=env,
                    capture_id=capture_id,
                    camera_id=f"cam_{i:02}",
                    storage_key=key,
                    sha256=checksum(raw),
                    width=320,
                    height=240,
                    original_width=320,
                    original_height=240,
                    exif_orientation=1,
                    content_type="image/png",
                )
            )
        conn.execute(update(captures).where(captures.c.id == capture_id).values(status="ready"))
    service = ProcessingService(
        repository, dispatcher, Settings(_env_file=None, vision_provider="fake")
    )
    try:
        first = service.schedule(capture_id)
        service.schedule(capture_id)
        assert dispatcher.queue.count == 1
        rq_id = f"vision-{first['job']['id']}-1"
        raw = dispatcher.connection.hget(f"rq:job:{rq_id}", "data")
        # RQ compresses the job's JSON transport bytes.
        import zlib

        decoded = json.loads(zlib.decompress(raw))
        assert decoded[0] == "scene_tracker.workers.jobs.run_vision"
        assert decoded[2] == [
            {"schema_version": 1, "job_id": str(first["job"]["id"]), "run_id": str(first["id"])}
        ]
        with engine.begin() as conn:
            conn.execute(
                update(captures).where(captures.c.id == capture_id).values(status="failed")
            )

        def burst():
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from scene_tracker.workers.vision import work; "
                    f"work(burst=True, queue_name={queue_name!r})",
                ],
                capture_output=True,
                text=True,
                timeout=40,
            )
            assert result.returncode == 0, result.stdout + result.stderr

        burst()
        assert repository.run(first["id"])["status"] == "failed"
        assert "invalid_capture" in repository.run(first["id"])["error"]
        with engine.begin() as conn:
            conn.execute(update(captures).where(captures.c.id == capture_id).values(status="ready"))
        retry = service.schedule(capture_id, retry=True)
        burst()
        assert repository.run(retry["id"])["status"] == "succeeded"
        rq_job = Job.fetch(
            f"vision-{first['job']['id']}-2",
            connection=dispatcher.connection,
            serializer=JSONSerializer,
        )
        rq_job.delete()
        assert repository.run(retry["id"])["status"] == "succeeded"
        assert repository.run(first["id"])["status"] == "failed"
    finally:
        dispatcher.queue.delete(delete_jobs=True)
        dispatcher.connection.close()
        for obj in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, obj.object_name)
        client.remove_bucket(bucket)

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
    execute_vision(
        api.services.repository,
        UUID(first["job"]["id"]),
        UUID(first["id"]),
        store_factory=api.services.store_factory,
    )
    assert api.services.repository.run(UUID(retry["id"]))["status"] == "queued"
    api.services.dispatcher.drain(
        lambda job, run: execute_vision(
            api.services.repository, UUID(job), UUID(run), store_factory=api.services.store_factory
        )
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


def test_synthetic_pipeline_downloads_and_traceability(api, tmp_path):
    import json
    import zipfile
    from urllib.request import urlopen

    from scene_tracker.domain.enums import CameraID
    from scene_tracker.vision.fixtures import synthetic_image

    env = api.client.post("/api/v1/environments", json={"name": "synthetic room"}).json()
    uploaded = api.client.post(
        f"/api/v1/environments/{env['id']}/captures",
        files=[(str(c), (f"{c}.png", synthetic_image(c), "image/png")) for c in CameraID],
    )
    assert uploaded.status_code == 201
    result = uploaded.json()
    queued = api.client.post(f"/api/v1/captures/{result['id']}/process", json={}).json()
    api.services.dispatcher.drain(
        lambda job, run: execute_vision(
            api.services.repository, UUID(job), UUID(run), store_factory=api.services.store_factory
        )
    )
    done = api.client.get(f"/api/v1/processing-runs/{queued['id']}").json()
    assert done["status"] == "succeeded"
    assert done["model_manifest"]["scope"] == "synthetic_fixture_pipeline"
    assert len(done["model_manifest"]["cameras"]) == 4
    detections = api.client.get(f"/api/v1/processing-runs/{queued['id']}/detections").json()[
        "items"
    ]
    assert len(detections) == 8
    per_camera = api.client.get(
        f"/api/v1/processing-runs/{queued['id']}/detections?camera_id=cam_04"
    ).json()["items"]
    assert len(per_camera) == 2
    debug = api.client.get(f"/api/v1/processing-runs/{queued['id']}/debug")
    assert debug.status_code == 200, debug.text
    artifacts = debug.json()["artifacts"]
    assert {a["camera_id"] for a in artifacts if a["camera_id"]} == set(CameraID)
    for kind in ["report", "inspection_bundle"]:
        artifact = next(a for a in artifacts if a["kind"] == kind)
        with urlopen(artifact["url"], timeout=10) as response:
            raw = response.read()
        name = "summary.html" if kind == "report" else "inspection.zip"
        (tmp_path / name).write_bytes(raw)
        if kind == "inspection_bundle":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                manifest = json.loads(archive.read("debug/manifest.json"))
                assert manifest["run_id"] == queued["id"]
                assert {c["frame_id"] for c in manifest["cameras"]} == {
                    f["id"] for f in result["frames"]
                }
                assert "debug/cam_04/crop_sheet.png" in archive.namelist()
                assert len([n for n in archive.namelist() if n.endswith(".f32")]) == 8
    # Permit an explicitly requested local inspection export without changing service test cleanup.
    if output := os.environ.get("SCENE_TRACKER_SMOKE_OUTPUT"):
        from pathlib import Path

        export = Path(output)
        export.mkdir(parents=True, exist_ok=True)
        for name in ("summary.html", "inspection.zip"):
            (export / name).write_bytes((tmp_path / name).read_bytes())
        (export / "run.json").write_text(json.dumps(done, indent=2))


def test_camera_failure_retry_keeps_stored_outputs(api):
    from scene_tracker.application.vision_pipeline import process_fake
    from scene_tracker.domain.enums import CameraID
    from scene_tracker.vision.detection.fake import FakeDetector
    from scene_tracker.vision.fixtures import synthetic_image

    class FaultyDetector(FakeDetector):
        def detect(self, image, prompts, config):
            if config[0].camera_id == CameraID.CAM_02:
                raise RuntimeError("injected cam_02 failure")
            return super().detect(image, prompts, config)

    env = api.services.repository.create_environment("fault fixture")
    uploaded = api.client.post(
        f"/api/v1/environments/{env['id']}/captures",
        files=[(str(c), (f"{c}.png", synthetic_image(c), "image/png")) for c in CameraID],
    ).json()
    path = f"/api/v1/captures/{uploaded['id']}/process"
    first = api.client.post(path, json={}).json()
    store = api.services.store_factory(env["id"])
    with pytest.raises(RuntimeError, match="injected cam_02"):
        api.services.dispatcher.drain(
            lambda job, run: execute_vision(
                api.services.repository,
                UUID(job),
                UUID(run),
                stage=lambda r, c: process_fake(
                    api.services.repository, r, c, store, detector=FaultyDetector()
                ),
            )
        )
    old_artifacts = api.services.repository.list_artifacts(UUID(first["id"]))
    old = {a["storage_key"]: store.get(store.stat(a["storage_key"])) for a in old_artifacts}
    failed = api.services.repository.run(UUID(first["id"]))
    assert failed["status"] == "failed"
    assert len(api.services.repository.list_detections(UUID(first["id"]))) == 6
    retry = api.client.post(path, json={"retry": True}).json()
    api.services.dispatcher.drain(
        lambda job, run: execute_vision(
            api.services.repository, UUID(job), UUID(run), store_factory=api.services.store_factory
        )
    )
    assert api.services.repository.run(UUID(retry["id"]))["status"] == "succeeded"
    for key, data in old.items():
        assert store.get(store.stat(key)) == data
    assert api.client.get(f"/api/v1/captures/{uploaded['id']}").json() == uploaded

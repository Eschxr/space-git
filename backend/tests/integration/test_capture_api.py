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
from scene_tracker.vision.detection.extractor_fake import FakeExtractor
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


def test_camera_commit_push_preserves_images_and_deduplicates_concurrent_retries(api):
    from scene_tracker.infrastructure.db.models import camera_commits, captures

    data = {
        "source_session_id": "saved-rig-session",
        "message": "Record the desk",
        "captured_at": "2026-11-15T10:00:00Z",
        "cam_04_captured_at": "2026-11-15T10:00:01Z",
    }
    with ThreadPoolExecutor(4) as pool:
        responses = list(
            pool.map(
                lambda _: api.client.post("/api/v1/camera-commits", data=data, files=files()),
                range(4),
            )
        )
    assert all(response.status_code == 201 for response in responses)
    first = responses[0].json()
    assert {response.json()["id"] for response in responses} == {first["id"]}
    assert first["message"] == "Record the desk" and first["parent_id"] is None
    assert first["run"]["status"] == "queued"
    assert len(api.services.dispatcher.pending) == 1
    with api.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(camera_commits)) == 1
        assert conn.scalar(select(func.count()).select_from(captures)) == 1
    saved = api.client.get(f"/api/v1/captures/{first['capture_id']}").json()
    assert [frame["camera_id"] for frame in saved["frames"]] == [f"cam_{i:02}" for i in range(1, 5)]
    assert saved["frames"][-1]["captured_at"] == "2026-11-15T10:00:01Z"
    for frame in saved["frames"]:
        raw = files()[0][1][1]
        blob = Blob(frame["storage_key"], frame["sha256"], frame["content_type"], len(raw))
        assert api.services.store_factory(UUID(first["environment_id"])).get(blob) == raw
    conflict = api.client.post(
        "/api/v1/camera-commits", data=data | {"message": "Different"}, files=files()
    )
    assert conflict.status_code == 409
    second = api.client.post(
        "/api/v1/camera-commits",
        data=data
        | {
            "source_session_id": "next-rig-session",
            "message": "Move the mug",
            "captured_at": "2026-11-15T10:05:00Z",
        },
        files=files(),
    ).json()
    assert second["parent_id"] == first["id"]
    history = api.client.get("/api/v1/camera-commits?limit=1").json()
    assert history["items"][0]["id"] == second["id"]
    assert api.client.get("/api/v1/camera-commits?offset=1").json()["items"][0]["id"] == first["id"]


def test_camera_commit_recovers_after_capture_saved_before_response(api, monkeypatch):
    from scene_tracker.application.captures import CaptureService

    original = CaptureService.ingest

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("connection interrupted after storage")

    data = {
        "source_session_id": "interrupted-session",
        "message": "Saved room",
        "captured_at": "2026-11-15T10:00:00Z",
    }
    monkeypatch.setattr(CaptureService, "ingest", interrupted)
    with pytest.raises(RuntimeError, match="connection interrupted"):
        api.client.post("/api/v1/camera-commits", data=data, files=files())
    assert api.client.get("/api/v1/camera-commits").json()["items"] == []
    monkeypatch.setattr(CaptureService, "ingest", original)
    response = api.client.post("/api/v1/camera-commits", data=data, files=files())
    assert response.status_code == 201
    assert len(api.client.get("/api/v1/camera-commits").json()["items"]) == 1


def test_camera_commit_persists_when_analysis_cannot_start(api):
    api.services.settings.vision_provider = "real"
    api.services.settings.vision = api.services.settings.vision.model_copy(
        update={"yoloe_checkpoint": None}
    )
    data = {
        "source_session_id": "missing-model-session",
        "message": "Camera evidence",
        "captured_at": "2026-11-15T10:00:00Z",
    }
    response = api.client.post("/api/v1/camera-commits", data=data, files=files())
    assert response.status_code == 201
    assert response.json()["processing_error"]
    assert response.json()["run"] is None
    assert len(api.client.get("/api/v1/camera-commits").json()["items"]) == 1
    saved = api.client.get(f"/api/v1/captures/{response.json()['capture_id']}").json()
    assert saved["status"] == "ready" and len(saved["frames"]) == 4
    assert api.services.dispatcher.pending == {}


def test_camera_commit_requires_complete_images_and_stable_timestamp(api):
    data = {
        "source_session_id": "incomplete-session",
        "message": "Camera evidence",
        "captured_at": "2026-11-15T10:00:00Z",
    }
    assert (
        api.client.post("/api/v1/camera-commits", data=data, files=files()[:3]).status_code == 422
    )
    assert (
        api.client.post(
            "/api/v1/camera-commits",
            data={"source_session_id": "no-time", "message": "Room"},
            files=files(),
        ).status_code
        == 422
    )
    assert api.client.get("/api/v1/camera-commits").json()["items"] == []


def capture(api):
    env = api.client.post("/api/v1/environments", json={"name": "room"})
    assert env.status_code == 201
    response = api.client.post(f"/api/v1/environments/{env.json()['id']}/captures", files=files())
    assert response.status_code == 201, response.text
    return response.json()


def test_saved_space_picker_reads_persisted_environments_in_pages(api):
    ids = [
        api.client.post("/api/v1/environments", json={"name": name}).json()["id"]
        for name in ["Lab", "Bedroom", "Office"]
    ]
    found = []
    for offset in range(3):
        page = api.client.get(f"/api/v1/environments?limit=1&offset={offset}")
        assert page.status_code == 200
        found.extend(item["id"] for item in page.json()["items"])
    assert found == list(reversed(ids))
    assert api.client.get("/api/v1/environments?offset=3").json()["items"] == []


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
    api.services.settings.vision = api.services.settings.vision.model_copy(
        update={"yoloe_checkpoint": None}
    )
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
                    api.services.repository,
                    r,
                    c,
                    store,
                    extractor=FakeExtractor(detector=FaultyDetector()),
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


def test_environment_prompt_catalogue_and_missing_models_before_enqueue(api):
    created = api.client.post(
        "/api/v1/environments",
        json={"name": "prompt-configured environment", "prompts": ["chair", "red toolbox"]},
    )
    assert created.status_code == 201
    assert created.json()["prompts"] == ["chair", "red toolbox"]
    assert api.services.repository.environment(UUID(created.json()["id"]))["prompts"] == [
        "chair",
        "red toolbox",
    ]
    assert (
        api.client.post("/api/v1/environments", json={"name": "bad", "prompts": [""]}).status_code
        == 422
    )
    result = capture(api)
    api.services.settings.vision_provider = "real"
    api.services.settings.vision.yoloe_checkpoint = None
    response = api.client.post(
        f"/api/v1/captures/{result['id']}/process", json={"preset": "default"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"
    with api.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(jobs)) == 0


def test_camera_tracks_miss_reappear_and_reference_validation(api):
    from sqlalchemy import select

    from scene_tracker.domain.enums import CameraID
    from scene_tracker.infrastructure.db.models import physical_objects, view_track_snapshots
    from scene_tracker.vision.fixtures import synthetic_image

    env = api.services.repository.create_environment("tracking lifecycle")

    def process_fixture(empty=False, moved=False):
        uploaded = api.client.post(
            f"/api/v1/environments/{env['id']}/captures",
            files=[
                (str(c), (f"{c}.png", synthetic_image(c, empty=empty, moved=moved), "image/png"))
                for c in CameraID
            ],
        ).json()
        run = api.client.post(f"/api/v1/captures/{uploaded['id']}/process", json={}).json()
        api.services.dispatcher.drain(
            lambda job, r: execute_vision(
                api.services.repository,
                UUID(job),
                UUID(r),
                store_factory=api.services.store_factory,
            )
        )
        with api.engine.connect() as conn:
            return (
                uploaded,
                run,
                [
                    dict(row.state)
                    for row in conn.execute(
                        select(view_track_snapshots).where(
                            view_track_snapshots.c.run_id == UUID(run["id"])
                        )
                    ).mappings()
                ],
            )

    first, run1, states1 = process_fixture()
    second, run2, states2 = process_fixture(moved=True)
    assert {s["view_track_id"] for s in states1} == {s["view_track_id"] for s in states2}
    _, _, missing = process_fixture(empty=True)
    assert all(s["status"] == "unobserved" and s["missing_count"] == 1 for s in missing)
    _, _, restored = process_fixture()
    assert {s["view_track_id"] for s in restored} == {s["view_track_id"] for s in states1}
    assert all(s["missing_count"] == 0 and s["before_missing_count"] == 1 for s in restored)
    track_id = states1[0]["view_track_id"]
    registry = api.client.get(f"/api/v1/view-tracks/{track_id}")
    assert registry.status_code == 200 and registry.json()["missing_count"] == 0
    history = api.client.get(f"/api/v1/view-tracks/{track_id}/history").json()
    assert len(history["items"]) == 4
    assert [r["state"]["status"] for r in history["items"]] == [
        "observed",
        "observed",
        "unobserved",
        "observed",
    ]
    assert all(
        r["run_status"] == "succeeded" and r["camera_id"] == registry.json()["camera_id"]
        for r in history["items"]
    )
    page = api.client.get(f"/api/v1/view-tracks/{track_id}/history?limit=1&offset=2").json()
    assert len(page["items"]) == 1 and page["items"][0]["state"]["missing_count"] == 1
    assert api.client.get(f"/api/v1/view-tracks/{uuid4()}/history").status_code == 404
    assert api.client.get(f"/api/v1/view-tracks/{track_id}/history?limit=101").status_code == 422

    groups = {c: {s["view_track_id"] for s in restored if s["camera_id"] == c} for c in CameraID}
    assert sum(len(x) for x in groups.values()) == len(set.union(*groups.values()))
    with api.engine.connect() as conn:
        assert not conn.execute(select(physical_objects)).first()
    assert (
        api.client.post(
            f"/api/v1/captures/{first['id']}/process", json={"reference_capture_id": second["id"]}
        ).status_code
        == 422
    )


def sequence_capture(api, env_id, *, moved=False, empty=False, added=False, captured_at=None):
    import json

    from PIL import PngImagePlugin

    from scene_tracker.domain.enums import CameraID
    from scene_tracker.vision.fixtures import METADATA_KEY, synthetic_image

    images = []
    for camera in CameraID:
        data = synthetic_image(camera, moved=moved, empty=empty)
        if added:
            image = Image.open(io.BytesIO(data))
            scenario = json.loads(image.info[METADATA_KEY])
            scenario["objects"].append(
                {
                    "id": "new-box",
                    "label": "box",
                    "box_xyxy": [140, 10, 180, 45],
                    "appearance_seed": f"{camera}-new-box",
                }
            )
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text(METADATA_KEY, json.dumps(scenario))
            stream = io.BytesIO()
            image.save(stream, format="PNG", pnginfo=metadata)
            data = stream.getvalue()
        images.append((str(camera), (f"{camera}.png", data, "image/png")))
    response = api.client.post(
        f"/api/v1/environments/{env_id}/captures",
        files=images,
        data={"captured_at": captured_at} if captured_at else {},
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    response = api.client.post(f"/api/v1/captures/{uploaded['id']}/process", json={})
    assert response.status_code == 202, response.text
    run = response.json()
    api.services.dispatcher.drain(
        lambda job, r: execute_vision(
            api.services.repository, UUID(job), UUID(r), store_factory=api.services.store_factory
        )
    )
    assert api.services.repository.run(UUID(run["id"]))["status"] == "succeeded"
    changes = api.client.get(f"/api/v1/processing-runs/{run['id']}/changes").json()["items"]
    return uploaded, run, changes


def approve_revision(api, env_id, uploaded, changes, key):
    for proposal in changes:
        response = api.client.post(
            f"/api/v1/change-proposals/{proposal['id']}/decision", json={"status": "accepted"}
        )
        assert response.status_code == 200, response.text
    body = {
        "capture_id": uploaded["id"],
        "proposal_ids": [p["id"] for p in changes],
        "idempotency_key": key,
        "message": key,
    }
    response = api.client.post(f"/api/v1/environments/{env_id}/revisions", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_review_revision_history_and_rejected_baseline(api):
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError

    from scene_tracker.infrastructure.db.models import revision_track_snapshots

    env_id = str(api.services.repository.create_environment("review sequence")["id"])
    first, _, changes1 = sequence_capture(api, env_id)
    assert len(changes1) == 8 and {c["type"] for c in changes1} == {"appeared_in_view"}
    revision1, _ = approve_revision(api, env_id, first, changes1, "baseline")
    snapshot1 = api.client.get(f"/api/v1/revisions/{revision1['id']}").json()
    second, _, changes2 = sequence_capture(api, env_id, moved=True, added=True)
    assert {c["type"] for c in changes2} == {"moved_in_view", "appeared_in_view"}
    rejected = next(
        c for c in changes2 if c["type"] == "moved_in_view" and c["camera_id"] == "cam_01"
    )
    assert rejected["before_ref"]["capture_id"] == first["id"]
    assert rejected["after_ref"]["capture_id"] == second["id"]
    assert rejected["before_ref"]["mask_url"] and rejected["after_ref"]["image_url"]
    api.client.post(
        f"/api/v1/change-proposals/{rejected['id']}/decision", json={"status": "rejected"}
    )
    accepted = [c for c in changes2 if c["id"] != rejected["id"]]
    revision2, body = approve_revision(api, env_id, second, accepted, "changes")
    assert (
        api.client.post(f"/api/v1/environments/{env_id}/revisions", json=body).json() == revision2
    )
    assert (
        api.client.post(
            f"/api/v1/environments/{env_id}/revisions", json=body | {"message": "different"}
        ).status_code
        == 409
    )
    changes = api.client.get(f"/api/v1/revisions/{revision2['id']}/diff").json()["changes"]
    assert {c["id"] for c in changes} == {c["id"] for c in accepted}
    assert rejected["id"] not in {c["id"] for c in changes}
    # Identical moved capture still proposes the previously rejected cam_01 move.
    _, _, changes3 = sequence_capture(api, env_id, moved=True, added=True)
    assert [(c["camera_id"], c["type"]) for c in changes3] == [("cam_01", "moved_in_view")]
    assert api.client.get(f"/api/v1/revisions/{revision1['id']}").json() == snapshot1
    assert (
        api.client.post(
            f"/api/v1/change-proposals/{accepted[0]['id']}/decision", json={"status": "rejected"}
        ).status_code
        == 409
    )
    assert (
        api.client.get(
            f"/api/v1/revisions/{revision2['id']}/diff?from_revision_id={uuid4()}"
        ).status_code
        == 422
    )
    assert (
        api.client.post(f"/api/v1/environments/{uuid4()}/revisions", json=body).status_code == 404
    )
    with pytest.raises(DBAPIError, match="immutable"):
        with api.engine.begin() as conn:
            conn.execute(update(revision_track_snapshots).values(state={}))
    # Missing is an image-view event, never physical removal.
    _, _, missing = sequence_capture(api, env_id, empty=True)
    assert {c["type"] for c in missing} == {"missing_from_view"}
    assert all(c["before_ref"] and c["after_ref"] is None for c in missing)


def test_highlight_api_temporal_roles_and_mock_export(api, tmp_path):
    import numpy as np

    from scene_tracker.domain.contracts import Mask
    from scene_tracker.geometry.point_grid import (
        GridTransform,
        colorize_point_grid,
        export_test_ply,
    )
    from scene_tracker.vision.masks import decode_mask

    env_id = str(api.services.repository.create_environment("highlights")["id"])
    first, _, changes = sequence_capture(api, env_id)
    approve_revision(api, env_id, first, changes, "initial")
    second, _, changes = sequence_capture(api, env_id, moved=True)
    revision, _ = approve_revision(api, env_id, second, changes, "move")
    query = f"?camera_id=cam_01&revision_id={revision['id']}"
    before = api.client.get(f"/api/v1/captures/{first['id']}/highlights{query}").json()
    after = api.client.get(f"/api/v1/captures/{second['id']}/highlights{query}").json()
    assert before["capture_id"] == first["id"] and after["capture_id"] == second["id"]
    assert {r["temporal_role"] for r in before["regions"]} == {"before"}
    assert {r["temporal_role"] for r in after["regions"]} == {"after"}
    assert before["regions"][0]["change_id"] == after["regions"][0]["change_id"]
    assert before["frame_id"] != after["frame_id"]
    assert after["camera_id"] == "cam_01" and len(after["regions"]) == 1
    store = api.services.store_factory(UUID(env_id))
    masks = {
        r["mask_ref"]: decode_mask(Mask.model_validate_json(store.get(store.stat(r["mask_ref"]))))
        for r in after["regions"]
    }
    h, w = after["image"]["height"], after["image"]["width"]
    y, x = np.indices((h, w))
    points = np.stack([x, y, np.ones_like(x)], axis=-1).astype(float)
    rgb = np.full((h, w, 3), 100, dtype=np.uint8)
    transform = GridTransform(
        image_width=w, image_height=h, crop_xyxy=(0, 0, w, h), resize_width=w, resize_height=h
    )
    xyz, colors, sidecar = colorize_point_grid(points, rgb, after, masks, transform)
    assert np.count_nonzero(sidecar["change_labels"]) == sum(m.sum() for m in masks.values())
    export_test_ply(tmp_path / "mock", xyz, colors, sidecar)
    # Missing objects appear only in the previous cloud, never on an empty current view.
    missing_capture, _, missing = sequence_capture(api, env_id, empty=True)
    missing_revision, _ = approve_revision(api, env_id, missing_capture, missing, "missing")
    query = f"?camera_id=cam_01&revision_id={missing_revision['id']}"
    missing_manifest = api.client.get(
        f"/api/v1/captures/{missing_capture['id']}/highlights{query}"
    ).json()
    assert missing_manifest["regions"] == []
    previous = api.client.get(f"/api/v1/captures/{second['id']}/highlights{query}").json()
    assert all(r["temporal_role"] == "before" for r in previous["regions"])
    other = capture(api)
    assert api.client.get(f"/api/v1/captures/{other['id']}/highlights{query}").status_code == 422
    assert (
        api.client.get(f"/api/v1/captures/{second['id']}/highlights?camera_id=cam_05").status_code
        == 422
    )


def test_full_fake_refactor_e2e(api, tmp_path):
    """One-command gate: real storage/DB, deterministic model fixtures, synthetic points."""
    import json
    import os
    from pathlib import Path

    import numpy as np

    from scene_tracker.domain.contracts import Mask
    from scene_tracker.geometry.point_grid import (
        GridTransform,
        colorize_point_grid,
        export_test_ply,
    )
    from scene_tracker.vision.masks import decode_mask

    output = Path(os.environ.get("SCENE_TRACKER_E2E_OUTPUT", tmp_path / "e2e"))
    output.mkdir(parents=True, exist_ok=False)
    env_id = str(api.services.repository.create_environment("full fake refactor smoke")["id"])
    first, run1, proposals1 = sequence_capture(api, env_id)
    rev1, _ = approve_revision(api, env_id, first, proposals1, "baseline")
    baseline = api.client.get(f"/api/v1/revisions/{rev1['id']}").json()
    second, run2, proposals2 = sequence_capture(api, env_id, moved=True, added=True)
    assert {p["type"] for p in proposals2} == {"moved_in_view", "appeared_in_view"}
    rev2, body = approve_revision(api, env_id, second, proposals2, "move-and-new")
    path = f"/api/v1/environments/{env_id}/revisions"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: api.client.post(path, json=body).json(), range(2)))
    assert results[0]["id"] == results[1]["id"] == rev2["id"]
    diff = api.client.get(f"/api/v1/revisions/{rev2['id']}/diff").json()
    assert len(diff["changes"]) == 8
    (output / "diff.json").write_text(json.dumps(diff, indent=2))
    store = api.services.store_factory(UUID(env_id))
    for capture_value, tag in ((first, "before"), (second, "after")):
        for frame in capture_value["frames"]:
            camera = frame["camera_id"]
            url = f"/api/v1/captures/{capture_value['id']}/highlights"
            manifest = api.client.get(
                url, params={"camera_id": camera, "revision_id": rev2["id"]}
            ).json()
            (output / f"{tag}-{camera}-manifest.json").write_text(json.dumps(manifest, indent=2))
            masks = {
                r["mask_ref"]: decode_mask(
                    Mask.model_validate_json(store.get(store.stat(r["mask_ref"])))
                )
                for r in manifest["regions"]
            }
            h, w = frame["height"], frame["width"]
            y, x = np.indices((h, w))
            points = np.stack([x / w, y / h, np.ones_like(x)], axis=-1).astype(float)
            # Original colors come from the canonical immutable image; synthetic XYZ only.
            from PIL import ImageOps

            original = store.get(store.stat(frame["storage_key"]))
            rgb = np.asarray(
                ImageOps.exif_transpose(Image.open(io.BytesIO(original))).convert("RGB")
            )
            transform = GridTransform(
                image_width=w,
                image_height=h,
                crop_xyxy=(0, 0, w, h),
                resize_width=w,
                resize_height=h,
            )
            xyz, colors, sidecar = colorize_point_grid(points, rgb, manifest, masks, transform)
            export_test_ply(output / f"{tag}-{camera}", xyz, colors, sidecar)
            # Preserve a source-colored synthetic cloud alongside its highlighted derivative.
            src_xyz, src_rgb, src_meta = colorize_point_grid(
                points, rgb, manifest | {"regions": []}, {}, transform
            )
            export_test_ply(output / f"{tag}-{camera}-source", src_xyz, src_rgb, src_meta)
    debug = api.client.get(f"/api/v1/processing-runs/{run2['id']}/debug").json()
    for artifact in debug["artifacts"]:
        if artifact["kind"] in ("report", "inspection_bundle"):
            name = "summary.html" if artifact["kind"] == "report" else "inspection.zip"
            (output / name).write_bytes(store.get(store.stat(artifact["storage_key"])))
    # Reprocessing is versioned and cannot alter accepted history.
    from scene_tracker.core.tracking_settings import TrackingSettings

    api.services.settings.tracking = TrackingSettings(movement_threshold=0.04)
    reprocess = api.client.post(f"/api/v1/captures/{second['id']}/process", json={}).json()
    assert reprocess["id"] != run2["id"]
    api.services.dispatcher.drain(
        lambda job, r: execute_vision(
            api.services.repository, UUID(job), UUID(r), store_factory=api.services.store_factory
        )
    )
    assert api.client.get(f"/api/v1/revisions/{rev1['id']}").json() == baseline
    # A subsequent worker failure leaves all originals and both revisions unchanged.
    failed_upload = api.client.post(f"/api/v1/environments/{env_id}/captures", files=files()).json()
    api.client.post(f"/api/v1/captures/{failed_upload['id']}/process", json={})

    def fail(*args):
        raise RuntimeError("intentional post-revision processing failure")

    with pytest.raises(RuntimeError, match="intentional"):
        api.services.dispatcher.drain(
            lambda job, r: execute_vision(api.services.repository, UUID(job), UUID(r), stage=fail)
        )
    assert api.client.get(f"/api/v1/revisions/{rev1['id']}").json() == baseline

    def without_urls(value):
        if isinstance(value, dict):
            return {
                k: without_urls(v)
                for k, v in value.items()
                if k != "url" and not k.endswith("_url")
            }
        if isinstance(value, list):
            return [without_urls(v) for v in value]
        return value

    refreshed = api.client.get(f"/api/v1/revisions/{rev2['id']}/diff").json()
    assert without_urls(refreshed) == without_urls(diff)
    assert api.client.get(f"/api/v1/captures/{first['id']}").json() == first
    assert api.client.get(f"/api/v1/captures/{second['id']}").json() == second
    (output / "summary.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "pretrained_inference": False,
                "pointdit_inference": False,
                "environment_id": env_id,
                "captures": [first["id"], second["id"]],
                "runs": [run1["id"], run2["id"]],
                "revisions": [rev1["id"], rev2["id"]],
                "note": "Test services are cleaned; local exports remain.",
            },
            indent=2,
        )
    )


def test_phase5_prototype_survives_missing_embedding_and_persists_diagnostics(api):
    import json

    from scene_tracker.application.vision_pipeline import process_fake
    from scene_tracker.infrastructure.db.models import view_track_snapshots

    env_id = str(api.services.repository.create_environment("prototype gap")["id"])
    first, run1, _ = sequence_capture(api, env_id)
    store = api.services.store_factory(UUID(env_id))
    with api.engine.connect() as conn:
        first_states = [
            dict(r.state)
            for r in conn.execute(
                select(view_track_snapshots).where(
                    view_track_snapshots.c.run_id == UUID(run1["id"])
                )
            ).mappings()
        ]
    chair = next(
        s
        for s in first_states
        if s["camera_id"] == "cam_01" and s["observation"]["label"] == "chair"
    )
    prototype = chair["appearance_prototype"]
    old_bytes = store.get(store.stat(prototype["embedding_key"]))
    uploaded = api.client.post(
        f"/api/v1/environments/{env_id}/captures",
        files=[
            (
                f["camera_id"],
                (f"{f['camera_id']}.png", store.get(store.stat(f["storage_key"])), "image/png"),
            )
            for f in first["frames"]
        ],
    ).json()
    gap_run = api.client.post(f"/api/v1/captures/{uploaded['id']}/process", json={}).json()

    class MissingMask(FakeExtractor):
        def extract(self, image, config):
            boxes, masks = super().extract(image, config)
            omitted = {b.id for b in boxes if b.camera_id == "cam_01" and b.label == "chair"}
            return boxes, [m for m in masks if m.detection_id not in omitted]

    api.services.dispatcher.drain(
        lambda job, run: execute_vision(
            api.services.repository,
            UUID(job),
            UUID(run),
            stage=lambda r, c: process_fake(
                api.services.repository, r, c, store, extractor=MissingMask()
            ),
        )
    )
    history_path = f"/api/v1/view-tracks/{chair['view_track_id']}/history"
    gap = api.client.get(history_path).json()["items"][-1]["state"]
    assert gap["observation"]["embedding_key"] is None
    assert gap["appearance_prototype"] == prototype
    assert gap["match"]["embedding_missing"] is True
    second, run2, _ = sequence_capture(api, env_id, moved=True)
    history = api.client.get(history_path).json()["items"]
    assert len(history) == 3
    restored = history[-1]["state"]
    assert restored["observation"]["capture_id"] == second["id"]
    assert restored["view_track_id"] == chair["view_track_id"]
    assert restored["match"]["terms"]["appearance"] == pytest.approx(1, abs=1e-5)
    assert restored["match"]["appearance_reference"] == prototype
    assert restored["appearance_prototype"]["detection_id"] == restored["observation"]["id"]
    assert history[0]["state"] == chair
    assert store.get(store.stat(prototype["embedding_key"])) == old_bytes
    assert api.services.repository.run(UUID(gap_run["id"]))["status"] == "succeeded"
    artifact = next(
        a
        for a in api.services.repository.list_artifacts(UUID(run2["id"]))
        if a["kind"] == "temporal_matches"
    )
    report = json.loads(store.get(store.stat(artifact["storage_key"])))
    assert report["schema_version"] == 2
    camera = report["cameras"]["cam_01"]
    assert camera["reference_run_id"] == gap_run["id"]
    assert camera["reference_kind"] == "processed_run"
    assert camera["screening"]["tracks"] and camera["unmatched_cost"] > 0
    assert all(c["reason_codes"] and c["cost_components"] for c in camera["candidates"])
    again = api.client.post(f"/api/v1/captures/{second['id']}/process", json={}).json()
    assert again["id"] == run2["id"]
    assert len(api.client.get(history_path).json()["items"]) == 3


def drain_vision(api):
    api.services.dispatcher.drain(
        lambda job, run: execute_vision(
            api.services.repository,
            UUID(job),
            UUID(run),
            store_factory=api.services.store_factory,
        )
    )


def test_phase6_discovery_and_reference_policy(api):
    env_id = str(api.services.repository.create_environment("workflow")["id"])
    initial, run, changes = sequence_capture(api, env_id)
    workflow_path = f"/api/v1/captures/{initial['id']}/workflow"
    workflow = api.client.get(workflow_path).json()
    assert workflow["outcome"] == "pending_review"
    assert len(workflow["source_images"]) == 4
    assert len(workflow["observed_tracks"]) == 8
    assert workflow["latest_run"]["reference"]["kind"] == "initial"
    revision, _ = approve_revision(api, env_id, initial, changes, "initial")
    assert api.client.get(workflow_path).json()["outcome"] == "committed"

    unapproved, _, _ = sequence_capture(api, env_id, moved=True)
    unchanged, same, no_changes = sequence_capture(api, env_id)
    assert not no_changes
    assert same["model_manifest"]["config"]["reference"]["revision_id"] == revision["id"]
    assert (
        api.client.get(f"/api/v1/captures/{unchanged['id']}/workflow").json()["outcome"]
        == "no_changes"
    )

    rerun = api.client.post(f"/api/v1/captures/{initial['id']}/process", json={}).json()
    assert rerun["id"] != run["id"]
    drain_vision(api)
    assert api.client.get(workflow_path).json()["outcome"] == "inspection_only"
    attempts = api.client.get(f"/api/v1/captures/{initial['id']}/processing-runs").json()["items"]
    assert [attempt["id"] for attempt in attempts] == [rerun["id"], run["id"]]
    assert attempts[0]["reference"]["inspection_reason"] == "approved_capture_rerun"
    assert attempts[1]["committed_revision_ids"] == [revision["id"]]

    debug = api.client.post(
        f"/api/v1/captures/{unapproved['id']}/process",
        json={"reference_capture_id": initial["id"]},
    ).json()
    drain_vision(api)
    assert (
        debug["model_manifest"]["config"]["reference"]["inspection_reason"] == "explicit_reference"
    )
    backdated, _, proposals = sequence_capture(
        api,
        env_id,
        captured_at="2000-01-01T00:00:00Z",
    )
    assert (
        api.client.get(f"/api/v1/captures/{backdated['id']}/workflow").json()["outcome"]
        == "inspection_only"
    )
    for item in proposals:
        api.client.post(
            f"/api/v1/change-proposals/{item['id']}/decision", json={"status": "accepted"}
        )
    response = api.client.post(
        f"/api/v1/environments/{env_id}/revisions",
        json={
            "capture_id": backdated["id"],
            "proposal_ids": [p["id"] for p in proposals],
            "idempotency_key": "backdated",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inspection_only"


def test_phase7_review_audit_idempotency_and_database_protection(api):
    from sqlalchemy import delete, update
    from sqlalchemy.exc import DBAPIError

    from scene_tracker.infrastructure.db.models import review_decisions

    env_id = str(api.services.repository.create_environment("audit")["id"])
    uploaded, _, proposals = sequence_capture(api, env_id)
    proposal = proposals[0]
    path = f"/api/v1/change-proposals/{proposal['id']}"
    with api.engine.connect() as conn:
        from scene_tracker.infrastructure.db.models import change_proposals

        original = dict(
            conn.execute(
                select(change_proposals).where(
                    change_proposals.c.id == UUID(proposal["id"]),
                )
            )
            .mappings()
            .one()
        )
    first = {
        "status": "accepted",
        "reason": "visible",
        "reviewer": "Alice",
        "idempotency_key": "one",
    }
    a = api.client.post(path + "/decision", json=first)
    assert a.status_code == 200
    assert (
        api.client.post(path + "/decision", json=first).json()["decision"] == a.json()["decision"]
    )
    assert (
        api.client.post(path + "/decision", json=first | {"reason": "different"}).status_code == 409
    )
    for status in ("rejected", "needs_review"):
        body = {"status": status, "reason": status, "reviewer": "Bob"}
        assert api.client.post(path + "/decision", json=body).status_code == 200
        assert api.client.post(path + "/decision", json=body).status_code == 200
    history = api.client.get(path + "/decisions").json()
    assert [row["previous_status"] for row in history["items"]] == [
        "proposed",
        "accepted",
        "rejected",
    ]
    assert [row["new_status"] for row in history["items"]] == [
        "accepted",
        "rejected",
        "needs_review",
    ]
    assert history["current_status"] == "needs_review"
    # Retrying an earlier decision does not reverse the newer decision.
    assert api.client.post(path + "/decision", json=first).json()["status"] == "needs_review"
    revision, _ = approve_revision(api, env_id, uploaded, [proposal], "selected")
    evidence = api.client.get(f"/api/v1/revisions/{revision['id']}/evidence").json()
    assert evidence["changes"][0]["review_decision"]["new_status"] == "accepted"
    assert api.client.post(path + "/decision", json={"status": "rejected"}).status_code == 409
    current = api.services.repository.run(UUID(proposal["run_id"]))
    changes = api.client.get(f"/api/v1/processing-runs/{current['id']}/changes").json()["items"]
    stored = next(item for item in changes if item["id"] == proposal["id"])
    with api.engine.connect() as conn:
        current = dict(
            conn.execute(
                select(change_proposals).where(
                    change_proposals.c.id == UUID(proposal["id"]),
                )
            )
            .mappings()
            .one()
        )
    assert {k: current[k] for k in ("before_ref", "after_ref", "evidence")} == {
        k: original[k] for k in ("before_ref", "after_ref", "evidence")
    }
    assert stored["status"] == "accepted"
    for statement in (update(review_decisions).values(reason="rewrite"), delete(review_decisions)):
        with pytest.raises(DBAPIError, match="immutable"):
            with api.engine.begin() as conn:
                conn.execute(statement)
    assert api.client.post(path + "/decision", json={"status": "proposed"}).status_code == 422


def test_phase8_multi_revision_image_history_and_endpoint_comparison(api):
    import hashlib
    from urllib.request import urlopen

    env_id = str(api.services.repository.create_environment("full history")["id"])
    first, _, changes = sequence_capture(api, env_id)
    r1, _ = approve_revision(api, env_id, first, changes, "baseline")
    original = api.client.get(f"/api/v1/revisions/{r1['id']}").json()
    unchanged, _, no_changes = sequence_capture(api, env_id)
    assert no_changes == []
    assert (
        api.client.get(f"/api/v1/captures/{unchanged['id']}/workflow").json()["outcome"]
        == "no_changes"
    )
    moved, _, changes = sequence_capture(api, env_id, moved=True, added=True)
    reject = next(p for p in changes if p["type"] == "moved_in_view" and p["camera_id"] == "cam_01")
    api.client.post(
        f"/api/v1/change-proposals/{reject['id']}/decision", json={"status": "rejected"}
    )
    r2, _ = approve_revision(
        api, env_id, moved, [p for p in changes if p["id"] != reject["id"]], "partial"
    )
    assert r2["parent_id"] == r1["id"]
    evidence_path = f"/api/v1/revisions/{r2['id']}/evidence"
    result = api.client.get(evidence_path)
    assert result.status_code == 200, result.text
    evidence = result.json()
    assert evidence["provenance"]["origin"] == "commit_snapshot"
    assert len(evidence["source_images"]) == 4
    assert len(evidence["approved_tracks"]) == 12
    retained = next(
        t for t in evidence["approved_tracks"] if t["view_track_id"] == reject["view_track_id"]
    )
    assert retained["observation"]["capture_id"] == first["id"]
    assert all(image["capture_id"] == moved["id"] for image in evidence["source_images"])
    assert retained["observation"]["overlays"]
    assert len(evidence["highlight_paths"]) == 8
    for frame in evidence["source_images"]:
        with urlopen(frame["image"]["url"], timeout=10) as response:
            assert hashlib.sha256(response.read()).hexdigest() == frame["sha256"]
    for asset in (
        retained["observation"]["mask"],
        retained["observation"]["crop"],
        *retained["observation"]["overlays"],
    ):
        with urlopen(asset["url"], timeout=10) as response:
            assert hashlib.sha256(response.read()).hexdigest() == asset["sha256"]
    rejected_history = api.client.get(
        f"/api/v1/view-tracks/{reject['view_track_id']}/revisions"
    ).json()
    assert [item["revision"]["id"] for item in rejected_history["items"]] == [r1["id"]]

    absent, _, missing = sequence_capture(api, env_id, empty=True)
    r3, _ = approve_revision(api, env_id, absent, missing, "missing")
    absent2, _, missing2 = sequence_capture(api, env_id, empty=True)
    assert all(p["evidence"]["state"]["missing_count"] == 2 for p in missing2)
    r4, _ = approve_revision(api, env_id, absent2, missing2, "still-missing")
    restored, _, proposals = sequence_capture(api, env_id, added=True)
    assert {p["type"] for p in proposals} == {"reappeared"}
    r5, _ = approve_revision(api, env_id, restored, proposals, "restored")
    assert [r3["parent_id"], r4["parent_id"], r5["parent_id"]] == [r2["id"], r3["id"], r4["id"]]
    compare = api.client.get(
        f"/api/v1/revisions/{r5['id']}/compare",
        params={"from_revision_id": r1["id"]},
    ).json()
    # Intermediate movement and missing events cancel at the endpoints.
    assert compare["direction"] == "forward"
    assert sum(item["kind"] == "unchanged" for item in compare["items"]) == 8
    assert sum(item["kind"] == "added" for item in compare["items"]) == 4
    event_log = api.client.get(
        f"/api/v1/revisions/{r5['id']}/diff",
        params={"from_revision_id": r1["id"]},
    ).json()["changes"]
    assert {e["type"] for e in event_log} == {
        "moved_in_view",
        "appeared_in_view",
        "missing_from_view",
        "reappeared",
    }
    reverse = api.client.get(
        f"/api/v1/revisions/{r1['id']}/compare",
        params={"from_revision_id": r5["id"]},
    ).json()
    assert reverse["direction"] == "reverse"
    assert sum(item["kind"] == "removed" for item in reverse["items"]) == 4
    identical = api.client.get(
        f"/api/v1/revisions/{r5['id']}/compare",
        params={"from_revision_id": r5["id"]},
    ).json()
    assert {item["kind"] for item in identical["items"]} == {"unchanged"}
    assert api.client.get(f"/api/v1/revisions/{r1['id']}").json() == original
    assert api.client.get(evidence_path).json()["provenance"] == evidence["provenance"]
    history = api.client.get(f"/api/v1/view-tracks/{reject['view_track_id']}/revisions").json()
    assert [r["revision"]["id"] for r in history["items"]] == [
        r1["id"],
        r3["id"],
        r4["id"],
        r5["id"],
    ]
    assert history["items"][-1]["before"]["state"]["status"] == "unobserved"


def test_phase8_competing_new_commits_and_stale_run_reprocessing(api):
    env_id = str(api.services.repository.create_environment("race")["id"])
    first, _, proposals = sequence_capture(api, env_id)
    baseline, _ = approve_revision(api, env_id, first, proposals, "base")
    a, run_a, proposals_a = sequence_capture(api, env_id, moved=True)
    b, _, proposals_b = sequence_capture(api, env_id, added=True)
    for item in proposals_a + proposals_b:
        api.client.post(
            f"/api/v1/change-proposals/{item['id']}/decision", json={"status": "accepted"}
        )
    bodies = [
        {
            "capture_id": cap["id"],
            "proposal_ids": [p["id"] for p in proposals],
            "idempotency_key": cap["id"],
        }
        for cap, proposals in ((a, proposals_a), (b, proposals_b))
    ]
    path = f"/api/v1/environments/{env_id}/revisions"
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda body: api.client.post(path, json=body), bodies))
    assert sorted(r.status_code for r in results) == [201, 409]
    loser = next(index for index, r in enumerate(results) if r.status_code == 409)
    assert results[loser].json()["error"]["code"] == "stale_baseline"
    assert len(api.client.get(path).json()["items"]) == 2
    stale_capture = (a, b)[loser]
    assert (
        api.client.get(f"/api/v1/captures/{stale_capture['id']}/workflow").json()["outcome"]
        == "stale_baseline"
    )
    refreshed = api.client.post(f"/api/v1/captures/{stale_capture['id']}/process", json={})
    assert refreshed.status_code == 202
    assert refreshed.json()["id"] != (run_a["id"] if loser == 0 else proposals_b[0]["run_id"])
    drain_vision(api)
    assert api.client.get(f"/api/v1/revisions/{baseline['id']}").status_code == 200


def test_phase8_cross_environment_invalid_selection_and_atomic_rollback(api, monkeypatch):
    from sqlalchemy import event

    from scene_tracker.infrastructure.db.models import revision_track_snapshots

    env_id = str(api.services.repository.create_environment("atomic")["id"])
    other_id = str(api.services.repository.create_environment("other")["id"])
    cap, _, proposals = sequence_capture(api, env_id)
    other, _, foreign = sequence_capture(api, other_id)
    for p in proposals + foreign:
        api.client.post(f"/api/v1/change-proposals/{p['id']}/decision", json={"status": "accepted"})
    body = {
        "capture_id": cap["id"],
        "proposal_ids": [p["id"] for p in proposals],
        "idempotency_key": "atomic",
    }
    path = f"/api/v1/environments/{env_id}/revisions"
    for invalid in (
        body | {"capture_id": other["id"]},
        body | {"proposal_ids": [foreign[0]["id"]]},
        body | {"proposal_ids": [str(uuid4())]},
    ):
        assert api.client.post(path, json=invalid).status_code == 422
    assert api.client.get(path).json()["items"] == []

    def fail_snapshot(conn, cursor, statement, params, context, executemany):
        if statement.startswith("INSERT INTO revision_track_snapshots"):
            raise RuntimeError("injected snapshot failure")

    event.listen(api.engine, "before_cursor_execute", fail_snapshot)
    try:
        with pytest.raises(RuntimeError, match="snapshot failure"):
            api.client.post(path, json=body)
    finally:
        event.remove(api.engine, "before_cursor_execute", fail_snapshot)
    assert api.client.get(path).json()["items"] == []
    with api.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(revision_track_snapshots)) == 0
    own_revision, _ = approve_revision(api, env_id, cap, proposals, "atomic")
    other_revision, _ = approve_revision(api, other_id, other, foreign, "foreign")
    assert (
        api.client.get(
            f"/api/v1/revisions/{own_revision['id']}/compare",
            params={"from_revision_id": other_revision["id"]},
        ).status_code
        == 422
    )


def test_phase6_queued_reference_survives_head_advance(api):
    from scene_tracker.vision.contracts import ProcessingManifest

    env_id = str(api.services.repository.create_environment("queued baseline")["id"])
    initial, _, initial_changes = sequence_capture(api, env_id)
    r1, _ = approve_revision(api, env_id, initial, initial_changes, "initial")
    changed, _, changes = sequence_capture(api, env_id, moved=True)
    store = api.services.store_factory(UUID(env_id))
    queued_capture = api.client.post(
        f"/api/v1/environments/{env_id}/captures",
        files=[
            (
                frame["camera_id"],
                (
                    frame["camera_id"] + ".png",
                    store.get(store.stat(frame["storage_key"])),
                    "image/png",
                ),
            )
            for frame in initial["frames"]
        ],
    ).json()
    queued = api.client.post(
        f"/api/v1/captures/{queued_capture['id']}/process",
        json={},
    ).json()
    r2, _ = approve_revision(api, env_id, changed, changes, "advance")
    drain_vision(api)
    actual = api.services.repository.run(UUID(queued["id"]))
    assert actual["status"] == "succeeded"
    assert ProcessingManifest.model_validate(actual["model_manifest"]).scheduled_at is not None
    assert actual["model_manifest"]["reference"]["revision_id"] == r1["id"]
    workflow = api.client.get(f"/api/v1/captures/{queued_capture['id']}/workflow").json()
    assert workflow["approved_revision_id"] == r2["id"]
    assert workflow["outcome"] == "stale_baseline"
    assert workflow["latest_run"]["reference"]["revision_id"] == r1["id"]


def test_phase7_accepting_uncertain_preserves_snapshot_and_missing_evidence(api, monkeypatch):
    from scene_tracker.application.vision_pipeline import process_fake

    env_id = str(api.services.repository.create_environment("uncertain review")["id"])
    initial, _, initial_changes = sequence_capture(api, env_id)
    approve_revision(api, env_id, initial, initial_changes, "initial")
    store = api.services.store_factory(UUID(env_id))
    uploaded = api.client.post(
        f"/api/v1/environments/{env_id}/captures",
        files=[
            (
                frame["camera_id"],
                (
                    frame["camera_id"] + ".png",
                    store.get(store.stat(frame["storage_key"])),
                    "image/png",
                ),
            )
            for frame in initial["frames"]
        ],
    ).json()
    run = api.client.post(f"/api/v1/captures/{uploaded['id']}/process", json={}).json()

    class Maskless(FakeExtractor):
        def extract(self, image, config):
            boxes, _ = super().extract(image, config)
            return boxes, []

    api.services.dispatcher.drain(
        lambda job, run_id: execute_vision(
            api.services.repository,
            UUID(job),
            UUID(run_id),
            stage=lambda r, c: process_fake(
                api.services.repository, r, c, store, extractor=Maskless()
            ),
        )
    )
    changes = api.client.get(f"/api/v1/processing-runs/{run['id']}/changes").json()["items"]
    assert {item["type"] for item in changes} == {"uncertain"}
    revision, _ = approve_revision(api, env_id, uploaded, changes, "uncertain")
    snapshot = api.client.get(f"/api/v1/revisions/{revision['id']}").json()
    assert all(track["uncertain"] for track in snapshot["tracks"])
    assert all(track["observation"]["mask_key"] is None for track in snapshot["tracks"])

    source_key = uploaded["frames"][0]["storage_key"]
    original_factory = api.services.store_factory

    class MissingSource:
        def __init__(self, base):
            self.base = base

        def stat(self, key):
            if key == source_key:
                raise FileNotFoundError(key)
            return self.base.stat(key)

        def presign(self, blob):
            return self.base.presign(blob)

    monkeypatch.setattr(
        api.services, "store_factory", lambda env: MissingSource(original_factory(env))
    )
    result = api.client.get(f"/api/v1/revisions/{revision['id']}/evidence")
    assert result.status_code == 200, result.text
    unavailable = result.json()["source_images"][0]["image"]
    assert unavailable["sha256"] == uploaded["frames"][0]["sha256"]
    assert unavailable["url"] is None and unavailable["unavailable_reason"] == "missing_blob"
    assert api.client.get(f"/api/v1/revisions/{revision['id']}").json() == snapshot

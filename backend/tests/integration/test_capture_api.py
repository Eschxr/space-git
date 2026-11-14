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


def sequence_capture(api, env_id, *, moved=False, empty=False, added=False):
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
    response = api.client.post(f"/api/v1/environments/{env_id}/captures", files=images)
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
            return {k: without_urls(v) for k, v in value.items() if not k.endswith("_url")}
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

"""Explicit service suite. Never substitutes SQLite or fake S3 for these gates."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from urllib.request import urlopen
from uuid import uuid4

import pytest
from alembic import command
from minio import Minio
from sqlalchemy import inspect
from sqlalchemy.exc import DBAPIError

from scene_tracker.infrastructure.db.models import captures, environments, frames, metadata
from scene_tracker.infrastructure.storage.base import StorageError
from scene_tracker.infrastructure.storage.s3 import S3Store

pytestmark = pytest.mark.integration


def test_migration_roundtrip(database):
    engine, config = database
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == set(metadata.tables) | {"alembic_version"}
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    assert "frames" in inspect(engine).get_table_names()


def test_capture_constraints_and_immutability(database):
    engine, config = database
    command.upgrade(config, "head")
    env, capture = uuid4(), uuid4()
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(environments.insert().values(id=env, name="test"))
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                captures.insert().values(
                    id=capture, environment_id=env, captured_at=now, status="ready"
                )
            )
    with engine.begin() as connection:
        connection.execute(
            captures.insert().values(
                id=capture, environment_id=env, captured_at=now, status="uploading"
            )
        )
        for camera in ("cam_01", "cam_02", "cam_03", "cam_04"):
            connection.execute(
                frames.insert().values(
                    environment_id=env,
                    capture_id=capture,
                    camera_id=camera,
                    storage_key=f"originals/{env}/{capture}/{camera}/test.png",
                    sha256="0" * 64,
                    width=12,
                    height=8,
                    original_width=12,
                    original_height=8,
                    exif_orientation=1,
                    content_type="image/png",
                )
            )
        connection.execute(captures.update().where(captures.c.id == capture).values(status="ready"))
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(frames.update().values(width=1))
    other_env = uuid4()
    with engine.begin() as connection:
        connection.execute(environments.insert().values(id=other_env, name="other"))
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                frames.insert().values(
                    environment_id=other_env,
                    capture_id=capture,
                    camera_id="cam_01",
                    storage_key="bad",
                    sha256="0" * 64,
                    width=1,
                    height=1,
                    original_width=1,
                    original_height=1,
                    exif_orientation=1,
                    content_type="image/png",
                )
            )


def test_s3_immutable_scoped_signed_download():
    endpoint = os.environ.get("TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.fail("Set TEST_S3_ENDPOINT, TEST_S3_ACCESS_KEY and TEST_S3_SECRET_KEY")
    client = Minio(
        endpoint,
        access_key=os.environ["TEST_S3_ACCESS_KEY"],
        secret_key=os.environ["TEST_S3_SECRET_KEY"],
        secure=False,
    )
    bucket = "test-" + uuid4().hex
    client.make_bucket(bucket)
    env = uuid4()
    store = S3Store(client, bucket, env)
    try:
        blob = store.put("vision/run/result.json", b"{}", "application/json")
        assert store.get(blob) == b"{}"
        assert store.put(blob.key, b"{}", blob.content_type) == blob
        with pytest.raises(StorageError):
            store.put(blob.key, b"changed", blob.content_type)
        with pytest.raises(StorageError):
            store.get(replace(blob, sha256="0" * 64))
        with urlopen(store.presign(blob), timeout=10) as response:
            assert response.read() == b"{}"
        with pytest.raises(Exception) as error:
            S3Store(client, bucket, uuid4()).get(blob)
        assert "NoSuchKey" in str(error.value)

        def put(data):
            try:
                return store.put("race", data, "application/octet-stream")
            except StorageError:
                return None

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(put, [b"first", b"second"]))
        assert sum(r is not None for r in results) == 1
    finally:
        for obj in client.list_objects(bucket, recursive=True):
            client.remove_object(bucket, obj.object_name)
        client.remove_bucket(bucket)


def test_object_link_environment_and_conflicts(database):
    from scene_tracker.infrastructure.db.models import (
        object_track_links,
        physical_objects,
        view_tracks,
    )

    engine, config = database
    command.upgrade(config, "head")
    env, other_env, obj, other_obj, track = (uuid4() for _ in range(5))
    with engine.begin() as connection:
        connection.execute(
            environments.insert(), [{"id": env, "name": "one"}, {"id": other_env, "name": "two"}]
        )
        connection.execute(
            physical_objects.insert(),
            [
                {
                    "id": obj,
                    "environment_id": env,
                    "label": "chair",
                    "status": "unknown",
                    "created_at": datetime.now(UTC),
                },
                {
                    "id": other_obj,
                    "environment_id": other_env,
                    "label": "chair",
                    "status": "unknown",
                    "created_at": datetime.now(UTC),
                },
            ],
        )
        connection.execute(
            view_tracks.insert().values(
                id=track,
                environment_id=env,
                camera_id="cam_01",
                status="observed",
                first_seen_at=datetime.now(UTC),
            )
        )
    base = dict(
        environment_id=env,
        view_track_id=track,
        source="manual",
        review_status="accepted",
        evidence={},
        active=True,
    )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                object_track_links.insert().values(**base, physical_object_id=other_obj)
            )
    with engine.begin() as connection:
        connection.execute(object_track_links.insert().values(**base, physical_object_id=obj))
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(object_track_links.insert().values(**base, physical_object_id=obj))


def test_legacy_revision_survives_additive_refactor(database):
    from sqlalchemy import insert, select

    from scene_tracker.infrastructure.db.models import change_proposals, processing_runs, revisions

    engine, config = database
    command.upgrade(config, "0003")
    env, cap, run, proposal, revision = [uuid4() for _ in range(5)]
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(insert(environments).values(id=env, name="legacy"))
        conn.execute(
            insert(captures).values(id=cap, environment_id=env, captured_at=now, status="uploading")
        )
        conn.execute(
            insert(processing_runs).values(
                id=run,
                environment_id=env,
                capture_id=cap,
                status="succeeded",
                model_manifest={},
                config_hash="old",
            )
        )
        # Core tables include new columns, so use frozen SQL for pre-migration inserts.
        from sqlalchemy import text

        conn.execute(
            text("""INSERT INTO change_proposals
            (id,environment_id,run_id,type,evidence,status)
            VALUES (:id,:env,:run,'unobserved','{}','proposed')"""),
            {"id": proposal, "env": env, "run": run},
        )
        conn.execute(
            text("""INSERT INTO revisions
            (id,environment_id,capture_id,created_at,message)
            VALUES (:id,:env,:cap,:now,'legacy immutable')"""),
            {"id": revision, "env": env, "cap": cap, "now": now},
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert (
            conn.scalar(select(change_proposals.c.type).where(change_proposals.c.id == proposal))
            == "unobserved"
        )
        assert (
            conn.scalar(select(revisions.c.message).where(revisions.c.id == revision))
            == "legacy immutable"
        )
    command.downgrade(config, "0003")
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert (
            conn.scalar(select(revisions.c.message).where(revisions.c.id == revision))
            == "legacy immutable"
        )

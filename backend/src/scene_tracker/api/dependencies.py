from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from minio import Minio
from sqlalchemy import create_engine

from scene_tracker.core.settings import Settings
from scene_tracker.infrastructure.db.repositories import Repository
from scene_tracker.infrastructure.queue.base import JobDispatcher
from scene_tracker.infrastructure.queue.rq import RQDispatcher
from scene_tracker.infrastructure.storage.base import ArtifactStore
from scene_tracker.infrastructure.storage.s3 import S3Store


@dataclass
class Services:
    repository: Repository
    store_factory: Callable[[UUID], ArtifactStore]
    dispatcher: JobDispatcher
    settings: Settings


def get_services(request: Request):
    with request.app.state.services_lock:
        return _get_or_create_services(request)


def _get_or_create_services(request):
    if request.app.state.services is not None:
        return request.app.state.services
    settings = request.app.state.settings
    # Engine creation is lazy and does not connect until an application query.
    engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    request.app.state.engine = engine
    client = Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        secure=settings.s3_secure,
    )
    public = Minio(
        settings.public_objectstore_endpoint,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        secure=settings.s3_secure,
    )
    services = Services(
        Repository(engine),
        lambda env: S3Store(client, settings.s3_bucket, env, public),
        RQDispatcher(settings.redis_url),
        settings,
    )
    request.app.state.services = services
    return services

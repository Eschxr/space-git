from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from sqlalchemy import create_engine

from scene_tracker.core.settings import Settings
from scene_tracker.infrastructure.db.repositories import Repository
from scene_tracker.infrastructure.queue.base import JobDispatcher
from scene_tracker.infrastructure.queue.rq import RQDispatcher
from scene_tracker.infrastructure.storage.base import ArtifactStore
from scene_tracker.infrastructure.storage.factory import s3_store_factory


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
    services = Services(
        Repository(engine),
        s3_store_factory(settings),
        RQDispatcher(settings.redis_url),
        settings,
    )
    request.app.state.services = services
    return services

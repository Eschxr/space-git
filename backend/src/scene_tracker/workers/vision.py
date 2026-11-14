"""Start an RQ SpawnWorker without initializing GPU models in its parent."""

from redis import Redis
from rq import Queue, SpawnWorker
from rq.serializers import JSONSerializer

from scene_tracker.core.logging import configure_logging
from scene_tracker.core.settings import Settings


def work(burst=False, queue_name="vision"):
    settings = Settings()
    configure_logging(settings.log_level)
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(queue_name, connection=connection, serializer=JSONSerializer)
    worker = SpawnWorker([queue], connection=connection, serializer="rq.serializers.JSONSerializer")
    worker.work(burst=burst)

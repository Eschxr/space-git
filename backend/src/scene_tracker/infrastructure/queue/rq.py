from redis import Redis
from rq import Queue
from rq.exceptions import DuplicateJobError
from rq.job import Callback
from rq.serializers import JSONSerializer


class RQDispatcher:
    def __init__(self, redis_url: str, queue_name: str = "vision"):
        self.connection = Redis.from_url(redis_url)
        self.queue = Queue(queue_name, connection=self.connection, serializer=JSONSerializer)

    def enqueue_vision(self, job_id: str, run_id: str, attempt: int) -> None:
        try:
            self.queue.enqueue_call(
                "scene_tracker.workers.jobs.run_vision",
                args=[{"schema_version": 1, "job_id": job_id, "run_id": run_id}],
                job_id=f"vision-{job_id}-{attempt}",
                unique=True,
                timeout=3600,
                result_ttl=300,
                on_failure=Callback("scene_tracker.workers.jobs.rq_failure"),
            )
        except DuplicateJobError:
            pass

    def enqueue_reconstruction(self, job_id: str) -> None:
        raise NotImplementedError("Reconstruction scheduling starts in Phase 9")

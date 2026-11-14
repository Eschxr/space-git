import hashlib
import json

from scene_tracker.core.errors import AppError


class ProcessingService:
    def __init__(self, repository, dispatcher, settings):
        self.repository = repository
        self.dispatcher = dispatcher
        self.settings = settings

    def schedule(self, capture_id, preset="skeleton", retry=False):
        if self.settings.vision_provider == "real":
            raise AppError(
                "model_unavailable", "Real adapters are not available until Phase 4", 503
            )
        config = {"preset": preset, "provider": self.settings.vision_provider}
        digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        job = self.repository.prepare_job(capture_id, config, digest, retry)
        if job["status"] == "queued":
            try:
                self.dispatcher.enqueue_vision(str(job["id"]), str(job["run_id"]), job["attempt"])
            except Exception as exc:
                self.repository.finish_job(job["id"], job["run_id"], "failed", "queue_unavailable")
                raise AppError(
                    "queue_unavailable",
                    "Unable to enqueue vision job",
                    503,
                    job_id=str(job["id"]),
                    processing_run_id=str(job["run_id"]),
                ) from exc
        return self.repository.run(job["run_id"])

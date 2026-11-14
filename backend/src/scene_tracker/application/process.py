import hashlib
import json

from scene_tracker.core.errors import AppError


class ProcessingService:
    def __init__(self, repository, dispatcher, settings):
        self.repository = repository
        self.dispatcher = dispatcher
        self.settings = settings

    def schedule(self, capture_id, preset="fake-fixture", retry=False):
        if self.settings.vision_provider == "real":
            from scene_tracker.vision.readiness import preflight

            self.repository.capture(capture_id)
            vision = self.settings.vision
            assets = preflight(vision)
            resolved = vision.model_dump(mode="json")
            resolved.update(
                yoloe_checkpoint=assets["checkpoints"]["yoloe"]["path"],
                dinov2_checkpoint=assets["checkpoints"]["dinov2"]["path"],
                dinov2_source_dir=assets["sources"]["dinov2"]["path"],
            )
            config = {
                "preset": "default",
                "provider": "real",
                "pipeline_version": "yoloe-v1",
                "vision": resolved,
                "assets": assets,
            }
        else:
            config = {
                "preset": "fake-fixture",
                "provider": "fake",
                "pipeline_version": "yoloe-fake-v1",
            }
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

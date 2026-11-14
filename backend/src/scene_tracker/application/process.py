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

            capture = self.repository.capture(capture_id)
            environment = self.repository.environment(capture["environment_id"])
            vision = self.settings.vision
            assets = preflight(vision)
            resolved = vision.model_dump(mode="json")
            for name, prefix in [
                ("groundingdino", "grounding"),
                ("sam2", "sam2"),
                ("dinov2", "dinov2"),
            ]:
                resolved[prefix + "_source_dir"] = assets["sources"][name]["path"]
                resolved[prefix + "_checkpoint"] = assets["checkpoints"][name]["path"]
            resolved["bert_dir"] = assets["bert"]["path"]
            resolved["model_cache_dir"] = str(vision.model_cache_dir.resolve())
            config = {
                "preset": "default",
                "provider": "real",
                "pipeline_version": "real-v1",
                "vision": resolved,
                "assets": assets,
                "prompts": environment["prompts"] or list(vision.prompts),
            }
        else:
            config = {"preset": "fake-fixture", "provider": "fake", "pipeline_version": "fake-v1"}
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

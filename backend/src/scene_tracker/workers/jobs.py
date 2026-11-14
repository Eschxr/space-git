"""Only primitive versioned IDs enter worker jobs. No GPU imports at module scope."""

import logging
from uuid import UUID

from scene_tracker.core.settings import Settings
from scene_tracker.infrastructure.db.repositories import Repository

logger = logging.getLogger(__name__)


def execute_vision(repository, job_id, run_id, stage=None, store_factory=None):
    if not repository.claim(job_id, run_id):
        return
    try:
        run = repository.run(run_id)
        capture = repository.capture(run["capture_id"])
        if capture["status"] != "ready" or len(capture["frames"]) != 4:
            raise ValueError("invalid_capture")
        if stage is not None:
            stage(run, capture)
        else:
            from scene_tracker.application.vision_pipeline import process_fake
            from scene_tracker.infrastructure.storage.factory import s3_store_factory

            factory = store_factory or s3_store_factory(Settings())
            store = factory(capture["environment_id"])
            if run["model_manifest"]["config"]["provider"] == "real":
                from scene_tracker.application.vision_pipeline import process_pipeline
                from scene_tracker.core.vision_settings import VisionSettings
                from scene_tracker.vision.readiness import ModelUnavailable, preflight
                from scene_tracker.vision.runtime import load_models

                config = run["model_manifest"]["config"]
                settings = VisionSettings.model_validate(config["vision"])
                if preflight(settings) != config["assets"]:
                    raise ModelUnavailable("model assets changed after enqueue")
                extractor, embedder, provenance = load_models(settings)
                process_pipeline(
                    repository,
                    run,
                    capture,
                    store,
                    extractor=extractor,
                    embedder=embedder,
                    model_provenance=provenance,
                )
            else:
                process_fake(repository, run, capture, store)
        repository.finish_job(job_id, run_id, "succeeded")
        logger.info(
            "Vision pipeline completed; inspect manifest for provider and execution evidence",
            extra={"correlation_id": str(run_id)},
        )
    except Exception as exc:
        repository.finish_job(
            job_id, run_id, "failed", f"{getattr(exc, 'code', type(exc).__name__)}: {exc}"
        )
        logger.exception("Vision job failed", extra={"correlation_id": str(run_id)})
        raise


def run_vision(payload):
    from sqlalchemy import create_engine

    if set(payload) != {"schema_version", "job_id", "run_id"} or payload["schema_version"] != 1:
        raise ValueError("unsupported worker payload")
    engine = create_engine(Settings().database_url.get_secret_value(), pool_pre_ping=True)
    try:
        execute_vision(Repository(engine), UUID(payload["job_id"]), UUID(payload["run_id"]))
    finally:
        engine.dispose()


def rq_failure(job, connection, exc_type, exc_value, traceback):
    """Persist failure even when RQ interrupts execution (e.g. timeout)."""
    from sqlalchemy import create_engine

    payload = job.args[0]
    engine = create_engine(Settings().database_url.get_secret_value())
    try:
        Repository(engine).finish_job(
            UUID(payload["job_id"]),
            UUID(payload["run_id"]),
            "failed",
            f"{exc_type.__name__}: {exc_value}",
        )
    finally:
        engine.dispose()

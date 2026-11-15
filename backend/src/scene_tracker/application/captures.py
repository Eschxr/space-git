from scene_tracker.application.ingest import ingest_capture
from scene_tracker.core.errors import AppError


class CaptureService:
    def __init__(self, repository, store_factory, settings):
        self.repository = repository
        self.store_factory = store_factory
        self.settings = settings

    def ingest(self, environment_id, captured_at, uploads, capture_id=None):
        capture_id = self.repository.begin_capture(environment_id, captured_at, capture_id)
        try:
            capture = ingest_capture(
                environment_id,
                captured_at,
                uploads,
                self.store_factory(environment_id),
                capture_id=capture_id,
                max_bytes=self.settings.max_image_bytes,
                max_pixels=self.settings.max_image_pixels,
                max_skew_seconds=self.settings.max_timestamp_skew_seconds,
            )
            self.repository.finish_capture(capture)
        except ValueError as exc:
            self.repository.fail_capture(capture_id, str(exc))
            raise AppError("invalid_capture", str(exc), 422, capture_id=str(capture_id)) from exc
        except Exception as exc:
            self.repository.fail_capture(capture_id, "capture_storage_failed")
            raise AppError(
                "storage_unavailable",
                "Capture could not be stored",
                503,
                capture_id=str(capture_id),
            ) from exc
        return self.repository.capture(capture_id)

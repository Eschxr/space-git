from scene_tracker.core.settings import Settings
from scene_tracker.infrastructure.storage import factory
from scene_tracker.infrastructure.storage.base import Blob
from scene_tracker.infrastructure.storage.s3 import S3Store


def test_public_signer_has_explicit_region_and_separate_browser_endpoint(monkeypatch):
    calls = []

    def client(endpoint, **options):
        calls.append((endpoint, options))
        return object()

    monkeypatch.setattr(factory, "Minio", client)
    settings = Settings(
        _env_file=None, s3_endpoint="silo:9000", public_objectstore_endpoint="127.0.0.1:9000"
    )
    factory.s3_store_factory(settings)
    assert [endpoint for endpoint, _ in calls] == ["silo:9000", "127.0.0.1:9000"]
    # Region discovery through the browser's localhost would fail inside the API container.
    assert all(options["region"] == "us-east-1" for _, options in calls)


def test_signed_json_downloads_preserve_images_and_use_safe_attachment_filename():
    calls = []

    class Signer:
        def presigned_get_object(self, *args, **options):
            calls.append(options)
            return "signed-url"

    store = S3Store(Signer(), "bucket", "environment")
    store.presign(Blob('mask"name.json', "hash", "application/json", 2))
    store.presign(Blob("image.png", "hash", "image/png", 2))
    assert calls[0]["response_headers"] == {
        "response-content-disposition": "attachment; filename*=UTF-8''mask%22name.json"
    }
    assert calls[1]["response_headers"] is None

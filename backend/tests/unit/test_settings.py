import pytest
from pydantic import ValidationError

from scene_tracker.core.settings import Settings


def test_defaults():
    settings = Settings(_env_file=None)
    assert settings.vision_provider == "fake"
    assert settings.s3_bucket == "scene-tracker"
    assert settings.max_image_bytes > 0


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("VISION_PROVIDER", "real")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    settings = Settings(_env_file=None)
    assert settings.vision_provider == "real"
    assert settings.s3_bucket == "test-bucket"


def test_invalid_provider():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, vision_provider="fallback")


def test_empty_optional_weight_paths(monkeypatch):
    monkeypatch.setenv("POINTDIT_CHECKPOINT", "")
    assert Settings(_env_file=None).pointdit_checkpoint is None

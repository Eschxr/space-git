"""CPU-only configuration; no model initialization or service connections."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from scene_tracker.core.vision_settings import VisionSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://scene_tracker:local-dev-change-me@localhost:5432/scene_tracker"
    )
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str = "localhost:9000"
    s3_access_key: SecretStr = SecretStr("scene_tracker")
    s3_secret_key: SecretStr = SecretStr("local-dev-change-me")
    s3_bucket: str = "scene-tracker"
    public_objectstore_endpoint: str = "localhost:9000"
    model_cache_dir: Path = Path("models")
    vision: VisionSettings = Field(default_factory=VisionSettings)
    vision_provider: Literal["fake", "real"] = "fake"
    pointdit_checkpoint: Path | None = None
    dinov3_weights_dir: Path | None = None
    pointdit_source_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    max_image_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    max_timestamp_skew_seconds: float = Field(default=2, ge=0)
    s3_secure: bool = False

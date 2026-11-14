from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from scene_tracker.domain.contracts import SHA256


class VisionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VISION_",
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        populate_by_name=True,
    )
    extractor: Literal["fake", "yoloe"] = "yoloe"
    yoloe_checkpoint: Path | None = Field(default=None, validation_alias="YOLOE_CHECKPOINT")
    yoloe_sha256: SHA256 | None = Field(default=None, validation_alias="YOLOE_SHA256")
    yoloe_confidence: float = Field(default=0.25, ge=0, le=1, validation_alias="YOLOE_CONFIDENCE")
    yoloe_imgsz: int = Field(default=640, ge=32, le=2048, validation_alias="YOLOE_IMGSZ")
    yoloe_device: str = Field(
        default="cpu", pattern=r"^(cpu|cuda(:[0-9]+)?)$", validation_alias="YOLOE_DEVICE"
    )
    device: str = Field(default="cpu", pattern=r"^(cpu|cuda(:[0-9]+)?)$")
    dinov2_source_dir: Path | None = None
    dinov2_checkpoint: Path | None = None
    dinov2_sha256: SHA256 | None = None
    embedder_model: Literal["dinov2_vits14"] = "dinov2_vits14"
    model_cache_dir: Path = Field(default=Path("models"), validation_alias="MODEL_CACHE_DIR")
    crop_padding: float = Field(default=0.1, ge=0, le=1)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    min_mask_pixels: int = Field(default=16, ge=1)

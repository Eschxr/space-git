from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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
    grounding_source_dir: Path | None = None
    sam2_source_dir: Path | None = None
    dinov2_source_dir: Path | None = None
    grounding_checkpoint: Path | None = None
    sam2_checkpoint: Path | None = None
    dinov2_checkpoint: Path | None = None
    grounding_sha256: SHA256 | None = None
    sam2_sha256: SHA256 | None = None
    dinov2_sha256: SHA256 | None = None
    bert_dir: Path | None = None
    bert_sha256: SHA256 | None = None
    device: str = Field(default="cpu", pattern=r"^(cpu|cuda(:[0-9]+)?)$")
    model_cache_dir: Path = Field(default=Path("models"), validation_alias="MODEL_CACHE_DIR")
    detector_model: Literal["groundingdino_swint_ogc"] = "groundingdino_swint_ogc"
    segmenter_model: Literal["sam2.1_hiera_small"] = "sam2.1_hiera_small"
    embedder_model: Literal["dinov2_vits14"] = "dinov2_vits14"
    box_threshold: float = Field(default=0.35, ge=0, le=1)
    text_threshold: float = Field(default=0.25, ge=0, le=1)
    nms_iou: float = Field(default=0.5, ge=0, le=1)
    crop_padding: float = Field(default=0.1, ge=0, le=1)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    prompts: tuple[str, ...] = Field(
        default=("chair", "table", "computer monitor", "box"), min_length=1, max_length=32
    )

    @model_validator(mode="after")
    def valid_prompts(self):
        if any(not p.strip() or len(p) > 80 or "." in p for p in self.prompts):
            raise ValueError("prompt catalogue requires nonempty phrases without dots")
        return self

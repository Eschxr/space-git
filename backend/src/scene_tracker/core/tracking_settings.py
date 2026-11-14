from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrackingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    appearance_weight: float = Field(default=0.45, ge=0)
    position_weight: float = Field(default=0.25, ge=0)
    iou_weight: float = Field(default=0.20, ge=0)
    class_weight: float = Field(default=0.10, ge=0)
    max_area_ratio: float = Field(default=8, ge=1)
    fallback_iou_gate: float = Field(default=0.2, ge=0, le=1)
    fallback_displacement_gate: float = Field(default=0.25, ge=0, le=2)
    minimum_score: float = Field(default=0.65, gt=0, le=1)
    margin: float = Field(default=0.08, ge=0, le=1)
    minimum_appearance: float = Field(default=0.55, ge=0, le=1)
    fallback_penalty: float = Field(default=0.2, ge=0, lt=1)
    movement_threshold: float = Field(default=0.035, gt=0, le=1)
    minimum_area: float = Field(default=0.0001, ge=0, le=1)
    appearance_change_threshold: float = Field(default=0.65, ge=0, le=1)
    area_change_ratio: float = Field(default=2.0, gt=1)

    @model_validator(mode="after")
    def weights(self):
        if (
            min(self.appearance_weight, self.position_weight, self.iou_weight, self.class_weight)
            < 0
            or sum(
                [self.appearance_weight, self.position_weight, self.iou_weight, self.class_weight]
            )
            <= 0
        ):
            raise ValueError("tracking weights must have positive total")
        return self

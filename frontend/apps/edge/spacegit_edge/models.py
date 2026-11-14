from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Pair = tuple[FiniteFloat, FiniteFloat]
Triple = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
Id = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
Size = Annotated[FiniteFloat, Field(gt=0, le=30)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Card(Strict):
    id: Id
    marker: int = Field(ge=4, le=249)
    name: str = Field(min_length=1, max_length=80)
    x: FiniteFloat
    y: FiniteFloat
    w: Size
    h: Size
    d: Size
    angle: FiniteFloat = Field(ge=-6.284, le=6.284)


class KeepOut(Strict):
    id: Id
    name: str = Field(min_length=1,max_length=64)
    x: FiniteFloat
    y: FiniteFloat
    w: Size
    h: Size


class PlacementRules(Strict):
    clearance_mm: Annotated[FiniteFloat,Field(ge=0,le=250)] = 12
    keep_out: list[KeepOut] = Field(default_factory=list,max_length=12)

    @model_validator(mode="after")
    def unique_zones(self):
        if len({z.id for z in self.keep_out})!=len(self.keep_out):
            raise ValueError("Duplicate keep-out ID")
        return self


class Scene(Strict):
    version: Literal[1] = 1
    id: Id
    name: str = Field(min_length=1, max_length=80)
    frame: Literal["wall-world-meters"] = "wall-world-meters"
    wall: tuple[Size, Size]
    objects: list[Card] = Field(max_length=40)
    constraints: PlacementRules | None = None

    @model_validator(mode="after")
    def unique(self):
        for field in ("id", "marker"):
            if len({getattr(o, field) for o in self.objects}) != len(self.objects):
                raise ValueError(f"Duplicate object {field}")
        return self


class ProjectionSettings(Strict):
    limit_px: Annotated[FiniteFloat, Field(ge=2, le=25)] = 12


class CalibrationSettings(ProjectionSettings):
    wall: tuple[Size, Size]
    marker_m: Annotated[FiniteFloat, Field(gt=.005, le=.5)]


class CalibrationInput(CalibrationSettings):
    output: tuple[Annotated[int, Field(ge=320, le=8192)], Annotated[int, Field(ge=240, le=8192)]]
    fit: list[Pair] = Field(min_length=6, max_length=6)
    check: list[Pair] = Field(min_length=6, max_length=6)


class ProjectionInput(ProjectionSettings):
    fit: list[Pair] = Field(min_length=6, max_length=6)
    check: list[Pair] = Field(min_length=6, max_length=6)


class WorkspaceInput(Strict):
    corners: tuple[Pair, Pair, Pair, Pair]
    size_m: tuple[Size, Size] | None = None


class TrackInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    box: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
    object_id: Id | None = None


class ObservationCommit(Strict):
    branch: Id
    expected: Id
    message: str = Field(min_length=1, max_length=120)


class CameraInput(Strict):
    index: int = Field(ge=0, le=15)
    width: int = Field(ge=320, le=3840)
    height: int = Field(ge=240, le=2160)
    dictionary: Literal["DICT_4X4_250", "DICT_5X5_250", "DICT_6X6_250"] = "DICT_4X4_250"


class Save(Strict):
    branch: Id = "main"
    message: str = Field(min_length=1, max_length=120)
    scene: Scene | None = None
    observed: bool = False
    expected: Id | None = None


class Branch(Strict):
    name: Id
    commit: Id


class Diff(Strict):
    before: Id
    after: Id


class Merge(Strict):
    target: Id
    source: Id
    approve: bool = False
    base_target: Id | None = None
    base_source: Id | None = None
    accept_candidate: bool = False
    rule_choice: Literal["target","source"] | None = None
    object_choices: dict[Id,Literal["target","source"]] = Field(default_factory=dict,max_length=40)
    candidate_id: Id | None = None


class Deploy(Strict):
    commit: Id
    object_id: Id | None = None
    tolerance_mm: Annotated[FiniteFloat, Field(ge=5, le=75)] = 25
    dwell_s: Annotated[FiniteFloat, Field(ge=.35, le=5)] = .7


class JobInput(Strict):
    photos: list[Id] = Field(min_length=6, max_length=80)
    quality: Literal["sparse", "mesh", "mesh_textured", "dense", "textured"] = "sparse"


class VisualTransform(Strict):
    commit: Id
    position_m: Triple = (0,0,0)
    rotation_deg: Triple = (0,0,0)
    scale: Annotated[FiniteFloat, Field(ge=.000001, le=10000)] = 1
    reference_m: Annotated[FiniteFloat, Field(gt=0, le=30)] | None = None
    reference_units: Annotated[FiniteFloat, Field(gt=0, le=1000000)] | None = None

    @model_validator(mode="after")
    def bounds(self):
        if max(map(abs,self.position_m))>100 or max(map(abs,self.rotation_deg))>360:
            raise ValueError("Transform exceeds the visual workspace range")
        if bool(self.reference_m)!=bool(self.reference_units):
            raise ValueError("Supply both scale reference lengths")
        if self.reference_m and self.reference_units:
            scale=self.reference_m/self.reference_units
            if not .000001<=scale<=10000:
                raise ValueError("Reference scale exceeds the supported range")
            self.scale=scale
        return self

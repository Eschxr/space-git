from enum import StrEnum


class CameraID(StrEnum):
    CAM_01 = "cam_01"
    CAM_02 = "cam_02"
    CAM_03 = "cam_03"
    CAM_04 = "cam_04"

    @property
    def role(self) -> str:
        return "overhead" if self == self.CAM_04 else "side"


class CaptureStatus(StrEnum):
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MODEL_UNAVAILABLE = "model_unavailable"
    BLOCKED_MISSING_WEIGHTS = "blocked_missing_weights"


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class TrackStatus(StrEnum):
    OBSERVED = "observed"
    UNOBSERVED = "unobserved"
    UNKNOWN = "unknown"


class ChangeType(StrEnum):
    ADDED = "added_candidate"
    MOVED = "moved_2d_candidate"
    APPEARANCE = "appearance_changed_candidate"
    UNOBSERVED = "unobserved"
    REMOVED = "removed_candidate"
    RELOCATION = "possible_relocation"
    UNCHANGED = "unchanged"

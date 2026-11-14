from uuid import UUID

from fastapi import APIRouter

from scene_tracker.api.routes.captures import ServicesDep
from scene_tracker.application.highlights import highlight_manifest
from scene_tracker.domain.enums import CameraID
from scene_tracker.geometry.highlights import HighlightManifest

router = APIRouter(prefix="/api/v1")


@router.get("/captures/{capture_id}/highlights", response_model=HighlightManifest)
def get_highlights(
    capture_id: UUID, camera_id: CameraID, services: ServicesDep, revision_id: UUID | None = None
):
    return highlight_manifest(services, capture_id, camera_id, revision_id)

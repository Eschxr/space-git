from uuid import UUID

from sqlalchemy import select

from scene_tracker.application.revisions import require
from scene_tracker.core.errors import AppError
from scene_tracker.geometry.highlights import HighlightManifest, HighlightRegion, ImageSpace
from scene_tracker.infrastructure.db.models import revision_changes, revisions

PALETTE = {
    "appeared_in_view": (0, 220, 80),
    "moved_in_view": (255, 196, 0),
    "appearance_changed": (70, 120, 255),
    "missing_from_view": (255, 60, 60),
    "reappeared": (0, 220, 220),
    "uncertain": (200, 100, 255),
}


def highlight_manifest(services, capture_id, camera_id, revision_id=None):
    capture = services.repository.capture(capture_id)
    if capture["status"] != "ready":
        raise AppError("capture_not_ready", "Capture has no complete canonical frames", 409)
    frame = next(f for f in capture["frames"] if f["camera_id"] == camera_id)
    store = services.store_factory(capture["environment_id"])
    with services.repository.engine.connect() as conn:
        query = select(revision_changes.c.applied_payload).where(
            revision_changes.c.environment_id == capture["environment_id"]
        )
        if revision_id:
            revision = require(
                conn.execute(select(revisions).where(revisions.c.id == revision_id))
                .mappings()
                .first()
            )
            if revision["environment_id"] != capture["environment_id"]:
                raise AppError(
                    "invalid_reference", "Revision belongs to a different environment", 422
                )
            query = query.where(revision_changes.c.revision_id == revision_id)
        regions = []
        for payload in conn.execute(query.order_by(revision_changes.c.proposal_id)).scalars():
            if payload.get("camera_id") != str(camera_id) or payload["type"] not in PALETTE:
                continue  # Historical physical-object events have no canonical view-local contract.
            for role in ("before", "after"):
                ref = payload.get(f"{role}_ref")
                if not ref or ref["capture_id"] != str(capture_id):
                    continue
                if ref["frame_id"] != str(frame["id"]):
                    raise AppError("invalid_evidence", "Highlight frame mismatch", 409)
                regions.append(
                    HighlightRegion(
                        change_id=UUID(payload["id"]),
                        view_track_id=UUID(payload["view_track_id"]),
                        change_type=payload["type"],
                        temporal_role=role,
                        detection_id=UUID(ref["id"]),
                        mask_ref=ref["mask_key"],
                        mask_url=store.presign(store.stat(ref["mask_key"]))
                        if ref["mask_key"]
                        else None,
                        unavailable_reason=None
                        if ref["mask_key"]
                        else "extractor_returned_no_mask",
                        bbox_xyxy=ref["box_xyxy"],
                        highlight_rgb=PALETTE[payload["type"]],
                    )
                )
    return HighlightManifest(
        capture_id=capture_id,
        camera_id=camera_id,
        frame_id=frame["id"],
        revision_id=revision_id,
        image=ImageSpace(width=frame["width"], height=frame["height"]),
        image_url=store.presign(store.stat(frame["storage_key"])),
        regions=tuple(regions),
    )

from uuid import UUID

from sqlalchemy import insert

from scene_tracker.core.tracking_settings import TrackingSettings
from scene_tracker.infrastructure.db.models import change_proposals
from scene_tracker.vision.changes.propose import propose


def persist_changes(repository, run, tracking):
    settings = TrackingSettings.model_validate(run["model_manifest"]["config"].get("tracking", {}))
    items = propose(run["id"], tracking["states"], settings)
    with repository.engine.begin() as conn:
        for item in items:
            conn.execute(
                insert(change_proposals).values(
                    **(
                        item
                        | {"id": UUID(item["id"]), "view_track_id": UUID(item["view_track_id"])}
                    ),
                    environment_id=run["environment_id"],
                    run_id=run["id"],
                    object_id=None,
                )
            )
    return items

"""Image-view hypotheses only; thresholds are configuration, not model accuracy claims."""

from uuid import UUID, uuid5

from scene_tracker.vision.matching.costs import geometry


def propose(run_id, states, settings):
    items = []
    for state in states:
        before, after = state.get("before"), state["observation"]
        terms = (state.get("match") or {}).get("terms", {})
        kind = None
        if state.get("uncertain"):
            kind = "uncertain"
        elif state["status"] == "unobserved":
            kind = "missing_from_view"
        elif before is None:
            kind = "appeared_in_view"
        elif state.get("before_missing_count", 0):
            kind = "reappeared"
        else:
            box = geometry(after)
            area = (box[2] - box[0]) * (box[3] - box[1])
            if area >= settings.minimum_area:
                if terms.get("displacement_norm", 0) > settings.movement_threshold:
                    kind = "moved_in_view"
                elif (
                    terms.get("appearance") is not None
                    and terms["appearance"] < settings.appearance_change_threshold
                ) or (terms.get("area_ratio", 1) >= settings.area_change_ratio):
                    kind = "appearance_changed"
        if (state.get("match") or {}).get("embedding_missing"):
            kind = "uncertain"
        if kind:
            items.append(
                {
                    "id": str(uuid5(UUID(str(run_id)), f"change:{state['view_track_id']}:{kind}")),
                    "camera_id": state["camera_id"],
                    "view_track_id": state["view_track_id"],
                    "type": kind,
                    "before_ref": before,
                    "after_ref": after if state["status"] == "observed" else None,
                    "evidence": {
                        "confidence": (state.get("match") or {}).get("score", 0),
                        "terms": terms,
                        "state": state,
                        "reference_revision_id": state.get("reference_revision_id"),
                        "reason": "ambiguous_or_insufficient_evidence"
                        if kind == "uncertain"
                        else "image_view_hypothesis_requires_review",
                    },
                    "status": "proposed",
                }
            )
    return items

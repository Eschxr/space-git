"""Deterministic camera-local assignment with explicit unmatched columns and ambiguity."""

import numpy as np
from scipy.optimize import linear_sum_assignment

from scene_tracker.vision.matching.costs import compare


def match(camera_id, old_tracks, new_detections, settings):
    old = sorted(old_tracks, key=lambda x: str(x["view_track_id"]))
    new = sorted(new_detections, key=lambda x: str(x["id"]))
    if any(x["camera_id"] != camera_id for x in [*old, *new]):
        raise ValueError("cross-camera matching is forbidden")
    if len({x["id"] for x in new}) != len(new) or len({x["view_track_id"] for x in old}) != len(
        old
    ):
        raise ValueError("duplicate tracking input")
    candidates = []
    unmatched_cost = 1 - settings.minimum_score
    matrix = np.full((len(old), len(new) + len(old)), unmatched_cost)
    for i, a in enumerate(old):
        for j, b in enumerate(new):
            item = compare(a, b, settings) | {
                "track_id": str(a["view_track_id"]),
                "detection_id": str(b["id"]),
                "row": i,
                "column": j,
                "decision": "gated",
                "reason_codes": [],
            }
            candidates.append(item)
            matrix[i, j] = item["cost"] if item["valid"] else 10
    ambiguous_rows, ambiguous_columns = set(), set()
    screenings = {"tracks": [], "detections": []}
    for axis, inputs, key, result_key in (
        ("row", old, "view_track_id", "tracks"),
        ("column", new, "id", "detections"),
    ):
        for index, value in enumerate(inputs):
            ranked = sorted(
                [c for c in candidates if c[axis] == index and c["valid"]],
                key=lambda c: (-c["score"], c["track_id"], c["detection_id"]),
            )
            eligible = [c for c in ranked if c["score"] > settings.minimum_score]
            top = ranked[:2]
            margin = top[0]["score"] - top[1]["score"] if len(top) > 1 else None
            ambiguous = len(eligible) > 1 and margin is not None and margin <= settings.margin
            screenings[result_key].append(
                {
                    "id": str(value[key]),
                    "top_two_scores": [c["score"] for c in top],
                    "top_two_candidates": [
                        {"track_id": c["track_id"], "detection_id": c["detection_id"]} for c in top
                    ],
                    "margin": margin,
                    "eligible_count": len(eligible),
                    "ambiguous": ambiguous,
                }
            )
            if ambiguous:
                for c in eligible:
                    ambiguous_rows.add(c["row"])
                    ambiguous_columns.add(c["column"])
    for c in candidates:
        if not c["valid"]:
            c["reason_codes"] = c["gate_reasons"]
        elif c["row"] in ambiguous_rows or c["column"] in ambiguous_columns:
            matrix[c["row"], c["column"]] = 10
            c.update(decision="ambiguous", reason_codes=["top_two_margin_too_small"])
        elif c["score"] <= settings.minimum_score:
            c.update(decision="below_threshold", reason_codes=["score_not_above_unmatched"])
        else:
            c.update(decision="alternative", reason_codes=["not_selected_by_assignment"])
    chosen = []
    if len(old):
        rows, cols = linear_sum_assignment(matrix)
        by_pair = {(c["row"], c["column"]): c for c in candidates}
        for i, j in zip(rows, cols, strict=True):
            if j < len(new) and matrix[i, j] < unmatched_cost:
                c = by_pair[i, j]
                c.update(decision="matched", reason_codes=["assigned_above_threshold_and_margin"])
                chosen.append(c)
    used_tracks = {c["track_id"] for c in chosen}
    used_detections = {c["detection_id"] for c in chosen}

    def unmatched(items, key, used, axis):
        result = []
        for index, item in enumerate(items):
            if str(item[key]) in used:
                continue
            considered = [c for c in candidates if c[axis] == index]
            reason = (
                "ambiguous"
                if any(c["decision"] == "ambiguous" for c in considered)
                else "no_candidates"
                if not considered
                else "no_valid_candidates"
                if not any(c["valid"] for c in considered)
                else "below_threshold"
                if not any(c["score"] > settings.minimum_score for c in considered if c["valid"])
                else "assignment_conflict"
            )
            result.append({"id": str(item[key]), "reason": reason})
        return result

    return {
        "schema_version": 2,
        "matches": chosen,
        "candidates": candidates,
        "uncertain_detections": [str(new[j]["id"]) for j in sorted(ambiguous_columns)],
        "uncertain_tracks": [str(old[i]["view_track_id"]) for i in sorted(ambiguous_rows)],
        "screening": screenings,
        "unmatched_tracks": unmatched(old, "view_track_id", used_tracks, "row"),
        "unmatched_detections": unmatched(new, "id", used_detections, "column"),
        "unmatched_cost": unmatched_cost,
        "weights": settings.model_dump(),
    }

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
    matrix = np.full((len(old), len(new) + len(old)), 1 - settings.minimum_score)
    for i, a in enumerate(old):
        for j, b in enumerate(new):
            item = compare(a, b, settings) | {
                "track_id": str(a["view_track_id"]),
                "detection_id": str(b["id"]),
                "row": i,
                "column": j,
                "decision": "gated",
            }
            candidates.append(item)
            matrix[i, j] = 1 - item["score"] if item["valid"] else 10
    ambiguous_rows, ambiguous_columns = set(), set()
    for axis, count in [("row", len(old)), ("column", len(new))]:
        for index in range(count):
            eligible = sorted(
                [
                    c
                    for c in candidates
                    if c[axis] == index and c["valid"] and c["score"] >= settings.minimum_score
                ],
                key=lambda c: -c["score"],
            )
            if len(eligible) > 1 and eligible[0]["score"] - eligible[1]["score"] <= settings.margin:
                for c in eligible:
                    ambiguous_rows.add(c["row"])
                    ambiguous_columns.add(c["column"])
    for c in candidates:
        if c["row"] in ambiguous_rows or c["column"] in ambiguous_columns:
            matrix[c["row"], c["column"]] = 10
            c["decision"] = "ambiguous"
        elif c["valid"]:
            c["decision"] = (
                "below_threshold" if c["score"] < settings.minimum_score else "alternative"
            )
    chosen = []
    if len(old):
        rows, cols = linear_sum_assignment(matrix)
        for i, j in zip(rows, cols, strict=True):
            if j < len(new) and matrix[i, j] < 1 - settings.minimum_score:
                c = next(c for c in candidates if c["row"] == i and c["column"] == j)
                c["decision"] = "matched"
                chosen.append(c)
    return {
        "matches": chosen,
        "candidates": candidates,
        "uncertain_detections": [str(new[j]["id"]) for j in sorted(ambiguous_columns)],
        "uncertain_tracks": [str(old[i]["view_track_id"]) for i in sorted(ambiguous_rows)],
        "weights": settings.model_dump(),
    }

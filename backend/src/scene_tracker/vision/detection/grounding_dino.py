"""Grounding DINO canonicalization/NMS. Model loading is injected or worker-local."""

import math
from uuid import uuid5

import numpy as np

from scene_tracker.vision.contracts import DetectionBox


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / area if area else 0


class GroundingDINO:
    def __init__(self, predict, settings):
        self.predict, self.settings = predict, settings
        self.last_candidates = []

    def detect(self, rgb_image, prompts, config):
        self.last_candidates = []
        context, _ = config
        caption = " . ".join(prompts) + " ."
        raw_boxes, raw_scores, phrases = self.predict(
            rgb_image, caption, self.settings.box_threshold, self.settings.text_threshold
        )
        raw_boxes, raw_scores = np.asarray(raw_boxes), np.asarray(raw_scores)
        if raw_boxes.shape != (len(phrases), 4) or raw_scores.shape != (len(phrases),):
            raise ValueError("Grounding DINO output shape mismatch")
        if not np.isfinite(raw_boxes).all() or not np.isfinite(raw_scores).all():
            raise ValueError("nonfinite detection output")
        candidates, discarded = [], []
        for index, (box, score, phrase) in enumerate(
            zip(raw_boxes, raw_scores, phrases, strict=True)
        ):
            if not 0 <= score <= 1 or not np.logical_and(box >= 0, box <= 1).all():
                raise ValueError("expected normalized cxcywh boxes and finite scores")
            cx, cy, width, height = box
            xyxy = (
                max(0, math.floor((cx - width / 2) * context.width)),
                max(0, math.floor((cy - height / 2) * context.height)),
                min(context.width, math.ceil((cx + width / 2) * context.width)),
                min(context.height, math.ceil((cy + height / 2) * context.height)),
            )
            label = " ".join(str(phrase).lower().strip().strip(".").split())
            if not label or width <= 0 or height <= 0 or xyxy[0] >= xyxy[2] or xyxy[1] >= xyxy[3]:
                discarded.append(
                    {
                        "query_index": index,
                        "normalized_cxcywh": box.tolist(),
                        "score": float(score),
                        "phrase": str(phrase),
                        "caption": caption,
                        "decision": "empty_phrase" if not label else "degenerate_box",
                    }
                )
                continue
            detection = DetectionBox(
                **context.model_dump(),
                id=uuid5(context.run_id, f"{context.frame_id}:grounding:{index}"),
                fixture_id=f"query-{index}",
                label=label,
                score=float(score),
                box_xyxy=xyxy,
            )
            candidates.append(
                {
                    "detection": detection,
                    "query_index": index,
                    "normalized_cxcywh": box.tolist(),
                    "caption": caption,
                    "decision": "below_threshold"
                    if score < self.settings.box_threshold
                    else "candidate",
                }
            )
        accepted = []
        for candidate in sorted(
            candidates, key=lambda c: (-c["detection"].score, c["query_index"])
        ):
            detection = candidate["detection"]
            if candidate["decision"] == "below_threshold":
                continue
            duplicate = next(
                (
                    old
                    for old in accepted
                    if old.label == detection.label
                    and iou(old.box_xyxy, detection.box_xyxy) > self.settings.nms_iou
                ),
                None,
            )
            candidate["decision"] = "suppressed_same_label_overlap" if duplicate else "kept"
            if duplicate:
                candidate["alternative_to"] = str(duplicate.id)
            else:
                accepted.append(detection)
        self.last_candidates = [
            {k: (v.model_dump(mode="json") if k == "detection" else v) for k, v in c.items()}
            for c in candidates
        ]
        self.last_candidates = sorted(
            self.last_candidates + discarded, key=lambda c: c["query_index"]
        )
        return accepted

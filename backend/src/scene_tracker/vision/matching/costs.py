import math

import numpy as np


def normalize_label(label):
    words = " ".join(label.lower().strip().split())
    words = {
        "chairs": "chair",
        "boxes": "box",
        "seats": "seat",
        "tables": "table",
        "monitors": "monitor",
    }.get(words, words)
    return {"seat": "chair", "carton": "box", "computer monitor": "monitor"}.get(words, words)


def geometry(item):
    x1, y1, x2, y2 = item["box_xyxy"]
    w, h = item["width"], item["height"]
    return x1 / w, y1 / h, x2 / w, y2 / h


def compare(old, new, settings):
    a, b = geometry(old), geometry(new)
    area_a, area_b = (a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    overlap = intersection / max(area_a + area_b - intersection, 1e-12)
    if old.get("mask") is not None and new.get("mask") is not None:
        from PIL import Image

        mask_a, mask_b = old["mask"], new["mask"]
        if mask_a.shape != mask_b.shape:
            mask_a = np.asarray(
                Image.fromarray(mask_a).resize(
                    (mask_b.shape[1], mask_b.shape[0]), Image.Resampling.NEAREST
                )
            )
        overlap = float(np.logical_and(mask_a, mask_b).sum()) / max(
            int(np.logical_or(mask_a, mask_b).sum()), 1
        )
    distance = math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)
    ratio = max(area_a, area_b) / max(min(area_a, area_b), 1e-12)
    appearance = None
    x, y = old.get("feature"), new.get("feature")
    if (
        x is not None
        and y is not None
        and old.get("embedding_model") == new.get("embedding_model")
        and x.shape == y.shape
    ):
        appearance = float(np.clip(np.dot(x, y), -1, 1))
    category = 1.0 if normalize_label(old["label"]) == normalize_label(new["label"]) else 0.4
    weights = settings
    terms = {
        "appearance": appearance,
        "position": max(0, 1 - distance / math.sqrt(2)),
        "iou": overlap,
        "class": category,
        "displacement_norm": distance,
        "area_ratio": ratio,
    }
    weighted = (
        weights.position_weight * terms["position"]
        + weights.iou_weight * overlap
        + weights.class_weight * category
    )
    denominator = weights.position_weight + weights.iou_weight + weights.class_weight
    if appearance is not None:
        weighted += weights.appearance_weight * max(0, appearance)
        denominator += weights.appearance_weight
    score = weighted / max(denominator, 1e-12)
    if appearance is None:
        score *= 1 - settings.fallback_penalty
    valid = ratio <= settings.max_area_ratio and (
        appearance is not None
        and appearance >= settings.minimum_appearance
        or overlap >= settings.fallback_iou_gate
        and distance <= settings.fallback_displacement_gate
    )
    return {
        "score": score,
        "valid": bool(valid),
        "terms": terms,
        "embedding_missing": appearance is None,
        "mask_iou": old.get("mask") is not None and new.get("mask") is not None,
    }

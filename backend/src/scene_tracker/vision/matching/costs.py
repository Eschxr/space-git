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
    terms = {
        "appearance": appearance,
        "position": max(0, 1 - distance / math.sqrt(2)),
        "iou": overlap,
        "class": category,
        "displacement_norm": distance,
        "area_ratio": ratio,
        "scale": 1 / ratio,
    }
    weights = {
        "appearance": settings.appearance_weight if appearance is not None else 0,
        "position": settings.position_weight,
        "iou": settings.iou_weight,
        "class": settings.class_weight,
        "scale": settings.scale_weight,
    }
    denominator = sum(weights.values())
    if denominator <= 0:
        # Appearance-only configuration with unavailable appearance has no usable signal.
        contributions = {name: 0.0 for name in weights}
        score = 0.0
    else:
        contributions = {
            name: weight * max(0, terms[name] or 0) / denominator
            for name, weight in weights.items()
        }
        score = sum(contributions.values())
    cost_components = {
        name: weight / denominator - contributions[name] if denominator > 0 else 0.0
        for name, weight in weights.items()
    }
    penalty = score * settings.fallback_penalty if appearance is None else 0.0
    cost_components["missing_embedding_penalty"] = penalty
    if denominator <= 0:
        cost_components["no_usable_signal"] = 1.0
    score = max(0.0, min(1.0, score - penalty))
    reasons = []
    if ratio > settings.max_area_ratio:
        reasons.append("area_ratio_exceeds_gate")
    if not (
        appearance is not None
        and appearance >= settings.minimum_appearance
        or overlap >= settings.fallback_iou_gate
        and distance <= settings.fallback_displacement_gate
    ):
        reasons.append("appearance_and_geometry_below_gates")
    if denominator <= 0:
        reasons.append("no_usable_signal")
    return {
        "score": score,
        "cost": 1 - score,
        "cost_components": cost_components,
        "score_components": contributions,
        "effective_weight_sum": denominator,
        "valid": not reasons,
        "gate_reasons": reasons,
        "terms": terms,
        "embedding_missing": appearance is None,
        "mask_iou": old.get("mask") is not None and new.get("mask") is not None,
        "appearance_reference": old.get("appearance_reference"),
    }

"""Prompt-free YOLOE conversion. No third-party Results escape this adapter."""

from uuid import uuid5

import numpy as np

from scene_tracker.vision.contracts import DetectionBox, InstanceMask
from scene_tracker.vision.masks import encode_mask


def array(value):
    return np.asarray(value.detach().cpu().numpy() if hasattr(value, "detach") else value)


class YOLOEExtractor:
    def __init__(self, model, settings):
        self.model, self.settings = model, settings
        self.last_candidates = []

    def extract(self, rgb_image, config):
        context, _ = config
        outputs = self.model.predict(
            source=rgb_image,
            conf=self.settings.yoloe_confidence,
            imgsz=self.settings.yoloe_imgsz,
            device=self.settings.yoloe_device,
            retina_masks=True,
            verbose=False,
            save=False,
        )
        if len(outputs) != 1:
            raise ValueError("YOLOE expected exactly one frame result")
        result = outputs[0]
        if tuple(result.orig_shape) != (context.height, context.width):
            raise ValueError("YOLOE original image dimensions mismatch")
        if result.boxes is None or len(result.boxes.xyxy) == 0:
            return [], []
        boxes, scores, classes = (
            array(result.boxes.xyxy),
            array(result.boxes.conf),
            array(result.boxes.cls),
        )
        if boxes.shape != (len(scores), 4) or classes.shape != scores.shape:
            raise ValueError("YOLOE box/score/class shape mismatch")
        masks = None if result.masks is None else array(result.masks.data)
        if masks is not None and masks.shape != (len(boxes), context.height, context.width):
            raise ValueError("retina masks must map exactly to canonical original image dimensions")
        detections, segments = [], []
        self.last_candidates = []
        for i, (bbox, score, cls) in enumerate(zip(boxes, scores, classes, strict=True)):
            if not np.isfinite(bbox).all() or not np.isfinite(cls) or int(cls) != cls:
                raise ValueError("invalid YOLOE geometry/class")
            bbox = np.clip(bbox, [0, 0, 0, 0], [context.width, context.height] * 2)
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                continue
            detection = DetectionBox(
                **context.model_dump(),
                id=uuid5(context.run_id, f"{context.frame_id}:yoloe:{i}"),
                fixture_id=f"query-{i}",
                label=result.names[int(cls)],
                score=float(score),
                box_xyxy=tuple(bbox),
            )
            detections.append(detection)
            if masks is not None:
                segments.append(
                    InstanceMask(
                        **context.model_dump(),
                        detection_id=detection.id,
                        rle=encode_mask(masks[i] > 0.5),
                        score=float(score),
                    )
                )
            self.last_candidates.append(
                {
                    "detection_id": str(detection.id),
                    "mask_missing": masks is None,
                    "transform": {
                        "orientation": "canonical",
                        "retina_masks": True,
                        "original_size": [context.width, context.height],
                    },
                }
            )
        return detections, segments

import numpy as np

from scene_tracker.vision.contracts import InstanceMask
from scene_tracker.vision.masks import encode_mask


class SAM2Segmenter:
    def __init__(self, predictor):
        self.predictor = predictor

    def segment(self, rgb_image, boxes, config):
        context, _ = config
        if not boxes:
            return []
        self.predictor.set_image(np.asarray(rgb_image))
        masks, scores, _ = self.predictor.predict(
            box=np.asarray([b.box_xyxy for b in boxes], dtype=np.float32), multimask_output=False
        )
        masks, scores = np.asarray(masks), np.asarray(scores)
        if len(boxes) == 1 and masks.shape == (1, context.height, context.width):
            masks = masks[:, None, :, :]
        if scores.shape == (len(boxes),):
            scores = scores[:, None]
        if masks.shape != (len(boxes), 1, context.height, context.width) or scores.shape != (
            len(boxes),
            1,
        ):
            raise ValueError("SAM 2 batch/mask dimensions mismatch")
        if not np.isfinite(scores).all() or not np.isin(masks, [0, 1]).all():
            raise ValueError("SAM 2 must return binary masks and finite quality scores")
        return [
            InstanceMask(
                **context.model_dump(),
                detection_id=box.id,
                rle=encode_mask(mask[0]),
                score=float(score[0]),
            )
            for box, mask, score in zip(boxes, masks, scores, strict=True)
        ]

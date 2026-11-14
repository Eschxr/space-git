import numpy as np

from scene_tracker.vision.contracts import InstanceMask
from scene_tracker.vision.masks import encode_mask


class FakeSegmenter:
    def segment(self, rgb_image, boxes, config):
        context, _ = config
        result = []
        for box in boxes:
            mask = np.zeros((context.height, context.width), dtype=np.uint8)
            x1, y1, x2, y2 = map(int, box.box_xyxy)
            mask[y1:y2, x1:x2] = 1
            result.append(
                InstanceMask(
                    **context.model_dump(), detection_id=box.id, rle=encode_mask(mask), score=1.0
                )
            )
        return result

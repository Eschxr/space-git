import math

import numpy as np
from PIL import Image

from scene_tracker.vision.contracts import ObjectEmbedding
from scene_tracker.vision.masks import decode_mask


def prepare_crop(rgb, mask, box, padding):
    x1, y1, x2, y2 = box.box_xyxy
    dx, dy = (x2 - x1) * padding, (y2 - y1) * padding
    bounds = (
        max(0, math.floor(x1 - dx)),
        max(0, math.floor(y1 - dy)),
        min(rgb.width, math.ceil(x2 + dx)),
        min(rgb.height, math.ceil(y2 + dy)),
    )
    masked = Image.new("RGB", rgb.size, (127, 127, 127))
    masked.paste(rgb, mask=Image.fromarray(decode_mask(mask.rle) * 255))
    crop = masked.crop(bounds)
    side = max(crop.size)
    square = Image.new("RGB", (side, side), (127, 127, 127))
    square.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
    square = square.resize((224, 224), Image.Resampling.BICUBIC)
    array = np.asarray(square, dtype=np.float32) / 255
    array = (array - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225], dtype=np.float32
    )
    return array.transpose(2, 0, 1).astype(np.float32)


class DINOv2Embedder:
    def __init__(self, forward, settings):
        self.forward, self.settings = forward, settings

    def embed(self, rgb_image, instance_masks, boxes, config):
        context, _ = config
        if [m.detection_id for m in instance_masks] != [b.id for b in boxes]:
            raise ValueError("embedding mask/box alignment mismatch")
        results = []
        batch_size = self.settings.embedding_batch_size
        for start in range(0, len(boxes), batch_size):
            batch = boxes[start : start + batch_size]
            inputs = np.stack(
                [
                    prepare_crop(rgb_image, mask, box, self.settings.crop_padding)
                    for mask, box in zip(
                        instance_masks[start : start + batch_size], batch, strict=True
                    )
                ]
            )
            outputs = np.asarray(self.forward(inputs), dtype=np.float32)
            if outputs.shape != (len(batch), 384) or not np.isfinite(outputs).all():
                raise ValueError("DINOv2 ViT-S/14 expects finite N x 384 output")
            norms = np.linalg.norm(outputs, axis=1)
            if np.any(norms <= 1e-12):
                raise ValueError("zero DINOv2 embedding")
            outputs = outputs / norms[:, None]
            results.extend(
                ObjectEmbedding(
                    **context.model_dump(),
                    detection_id=box.id,
                    values=tuple(vector),
                    dimension=384,
                    model="dinov2_vits14",
                )
                for box, vector in zip(batch, outputs, strict=True)
            )
        return results

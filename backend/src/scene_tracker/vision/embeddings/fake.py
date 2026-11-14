import hashlib

import numpy as np

from scene_tracker.vision.contracts import ObjectEmbedding


class FakeEmbedder:
    def embed(self, rgb_image, instance_masks, boxes, config):
        context, scenario = config
        seeds = {obj.id: obj.appearance_seed for obj in scenario.objects}
        result = []
        for box in boxes:
            raw = hashlib.sha256(seeds[box.fixture_id].encode()).digest()
            values = np.frombuffer(raw, dtype="<u4").astype(np.float64) / (2**32 - 1) - 0.5
            values = (values / np.linalg.norm(values)).astype(np.float32)
            result.append(
                ObjectEmbedding(
                    **context.model_dump(), detection_id=box.id, values=tuple(values), dimension=8
                )
            )
        return result

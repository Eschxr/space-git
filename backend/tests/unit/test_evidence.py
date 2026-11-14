from uuid import uuid4

import numpy as np
from PIL import Image

from scene_tracker.vision.contracts import DetectionBox, FrameContext, InstanceMask
from scene_tracker.vision.embeddings.dinov2 import crop_metadata, prepare_crop
from scene_tracker.vision.masks import decode_mask, encode_mask


def test_edge_overlapping_masks_and_exact_crop_transform():
    ctx = FrameContext(
        run_id=uuid4(), frame_id=uuid4(), camera_id="cam_04", width=64, height=64, trace_id="pixels"
    )
    rgb = Image.new("RGB", (64, 64), "white")
    for n, bounds in enumerate([(0, 0, 32, 16), (16, 8, 64, 64)]):
        box = DetectionBox(
            **ctx.model_dump(), id=uuid4(), fixture_id=str(n), label="box", score=1, box_xyxy=bounds
        )
        data = np.zeros((64, 64), dtype=np.uint8)
        x1, y1, x2, y2 = bounds
        data[y1:y2, x1:x2] = 1
        mask = InstanceMask(**ctx.model_dump(), detection_id=box.id, score=1, rle=encode_mask(data))
        assert np.array_equal(decode_mask(mask.rle), data)
        first = prepare_crop(rgb, mask, box, 0.1)
        assert np.array_equal(first, prepare_crop(rgb, mask, box, 0.1))
        assert first.shape == (3, 224, 224)
        transform = crop_metadata(rgb, box, 0.1)
        assert transform["canonical_crop_xyxy"][0] >= 0
        assert transform["canonical_crop_xyxy"][2] <= 64

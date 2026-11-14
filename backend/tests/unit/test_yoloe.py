from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from scene_tracker.core.vision_settings import VisionSettings
from scene_tracker.vision.contracts import FrameContext
from scene_tracker.vision.detection.yoloe import YOLOEExtractor
from scene_tracker.vision.masks import decode_mask
from scene_tracker.vision.readiness import ModelUnavailable, preflight


def test_prompt_free_results_and_missing_masks():
    ctx = FrameContext(
        run_id=uuid4(), frame_id=uuid4(), camera_id="cam_04", width=64, height=64, trace_id="test"
    )
    result = SimpleNamespace(
        orig_shape=(64, 64),
        names={0: "chair", 1: "box"},
        boxes=SimpleNamespace(
            xyxy=np.array([[0, 0, 20, 20], [20, 20, 64, 64]]),
            conf=np.array([0.9, 0.8]),
            cls=np.array([0, 1]),
        ),
        masks=SimpleNamespace(data=np.ones((2, 64, 64))),
    )

    class Model:
        def predict(self, **kwargs):
            assert kwargs["retina_masks"] is True
            assert "classes" not in kwargs and "prompts" not in kwargs
            return [result]

        def set_classes(self, *args):
            pytest.fail("prompt-free extraction must never set_classes")

    adapter = YOLOEExtractor(Model(), VisionSettings(_env_file=None))
    detections, masks = adapter.extract(Image.new("RGB", (64, 64)), (ctx, None))
    assert [d.label for d in detections] == ["chair", "box"]
    assert all(m.camera_id == "cam_04" and decode_mask(m.rle).shape == (64, 64) for m in masks)
    result.masks = None
    assert len(adapter.extract(None, (ctx, None))[0]) == 2
    assert adapter.extract(None, (ctx, None))[1] == []
    result.boxes = None
    assert adapter.extract(None, (ctx, None)) == ([], [])


def test_yoloe_readiness_is_local_and_does_not_require_old_models(tmp_path):
    from scene_tracker.vision.readiness import sha256_file

    checkpoint = tmp_path / "yoloe-11s-seg-pf.pt"
    dino = tmp_path / "dino.pth"
    checkpoint.write_bytes(b"stub asset, never executed")
    dino.write_bytes(b"stub embedding asset")
    settings = VisionSettings(
        _env_file=None,
        yoloe_checkpoint=checkpoint,
        yoloe_sha256=sha256_file(checkpoint),
        dinov2_checkpoint=dino,
        dinov2_sha256=sha256_file(dino),
        dinov2_source_dir=tmp_path,
    )
    ready = preflight(settings, source_verifier=lambda path, _: str(path))
    assert set(ready["checkpoints"]) == {"yoloe", "dinov2"}
    checkpoint.write_bytes(b"changed")
    with pytest.raises(ModelUnavailable, match="SHA-256"):
        preflight(settings)


@pytest.mark.parametrize(
    "case", ["mask_shape", "mask_nan", "mask_nonbinary", "dimensions", "score_shape"]
)
def test_invalid_results_fail_explicitly(case):
    ctx = FrameContext(
        run_id=uuid4(), frame_id=uuid4(), camera_id="cam_01", width=4, height=4, trace_id="invalid"
    )
    result = SimpleNamespace(
        orig_shape=(4, 4),
        names={0: "chair"},
        boxes=SimpleNamespace(
            xyxy=np.array([[0, 0, 4, 4]]), conf=np.array([0.9]), cls=np.array([0])
        ),
        masks=SimpleNamespace(data=np.ones((1, 4, 4))),
    )
    if case == "mask_shape":
        result.masks.data = np.ones((1, 2, 2))
    elif case == "mask_nan":
        result.masks.data[0, 0, 0] = np.nan
    elif case == "mask_nonbinary":
        result.masks.data[0, 0, 0] = 2
    elif case == "dimensions":
        result.orig_shape = (8, 8)
    elif case == "score_shape":
        result.boxes.conf = np.ones((1, 1))
    model = SimpleNamespace(predict=lambda **kwargs: [result])
    with pytest.raises(ValueError):
        YOLOEExtractor(model, VisionSettings(_env_file=None)).extract(None, (ctx, None))

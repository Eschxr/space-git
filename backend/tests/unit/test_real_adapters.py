from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from scene_tracker.core.legacy_vision_settings import VisionSettings
from scene_tracker.vision.contracts import DetectionBox, FrameContext
from scene_tracker.vision.detection.grounding_dino import GroundingDINO
from scene_tracker.vision.embeddings.dinov2 import DINOv2Embedder, prepare_crop
from scene_tracker.vision.masks import decode_mask
from scene_tracker.vision.segmentation.sam2 import SAM2Segmenter


def context():
    return FrameContext(
        run_id=uuid4(),
        frame_id=uuid4(),
        camera_id="cam_01",
        width=320,
        height=240,
        trace_id="contract-test",
    )


def box(ctx):
    return DetectionBox(
        **ctx.model_dump(),
        id=uuid4(),
        fixture_id="upstream-query",
        label="chair",
        score=0.9,
        box_xyxy=(80, 60, 240, 180),
    )


class PredictorStub:
    def __init__(self):
        self.encodings = 0
        self.calls = 0

    def set_image(self, image):
        assert image.shape == (240, 320, 3)
        self.encodings += 1

    def predict(self, *, box, multimask_output):
        self.calls += 1
        assert box.shape[1] == 4 and not multimask_output
        masks = np.zeros((len(box), 1, 240, 320), dtype=bool)
        for index, (x1, y1, x2, y2) in enumerate(box.astype(int)):
            masks[index, 0, y1:y2, x1:x2] = True
        return masks, np.full((len(box), 1), 0.95), None


def test_detector_normalized_boxes_nms_and_alternatives():
    ctx = context()
    image = Image.new("RGB", (ctx.width, ctx.height))
    settings = VisionSettings(_env_file=None)

    def upstream(rgb, caption, box_threshold, text_threshold):
        assert rgb is image
        assert caption == "chair . box ."
        assert (box_threshold, text_threshold) == (0.35, 0.25)
        return (
            np.array([[0.5, 0.5, 0.5, 0.5]] * 4),
            np.array([0.9, 0.8, 0.7, 0.1]),
            ["chair", "chair", "box", "chair"],
        )

    adapter = GroundingDINO(upstream, settings)
    results = adapter.detect(image, ["chair", "box"], (ctx, None))
    assert len(results) == 2
    assert results[0].box_xyxy == (80, 60, 240, 180)
    assert {d.label for d in results} == {"chair", "box"}
    assert {c["decision"] for c in adapter.last_candidates} == {
        "kept",
        "suppressed_same_label_overlap",
        "below_threshold",
    }
    assert results == adapter.detect(image, ["chair", "box"], (ctx, None))


@pytest.mark.parametrize("case", ["empty", "shape", "nan", "out_of_range"])
def test_detector_zero_and_invalid_output(case):
    ctx = context()
    boxes, scores, labels = np.empty((0, 4)), np.empty(0), []
    if case == "shape":
        boxes, scores, labels = np.zeros((1, 3)), np.ones(1), ["chair"]
    elif case == "nan":
        boxes, scores, labels = np.full((1, 4), np.nan), np.ones(1), ["chair"]
    elif case == "out_of_range":
        boxes, scores, labels = np.full((1, 4), 2), np.ones(1), ["chair"]
    adapter = GroundingDINO(lambda *args: (boxes, scores, labels), VisionSettings(_env_file=None))
    if case == "empty":
        assert adapter.detect(None, ["chair"], (ctx, None)) == []
    else:
        with pytest.raises(ValueError):
            adapter.detect(None, ["chair"], (ctx, None))


def test_sam_batch_mask_rle_and_one_encoding():
    ctx = context()
    boxes = [box(ctx), box(ctx)]
    predictor = PredictorStub()
    results = SAM2Segmenter(predictor).segment(Image.new("RGB", (320, 240)), boxes, (ctx, None))
    assert predictor.encodings == predictor.calls == 1
    assert [m.detection_id for m in results] == [b.id for b in boxes]
    for result in results:
        array = decode_mask(result.rle)
        assert array.shape == (240, 320) and array.sum() == 160 * 120
    assert SAM2Segmenter(predictor).segment(None, [], (ctx, None)) == []
    assert predictor.encodings == 1


@pytest.mark.parametrize("case", ["shape", "nonbinary", "bad_scores"])
def test_sam_invalid_outputs(case):
    class Invalid(PredictorStub):
        def predict(self, **kwargs):
            shape = (1, 1, 240, 320) if case != "shape" else (1, 1, 4, 4)
            return (
                np.full(shape, 2 if case == "nonbinary" else 0),
                np.array([[np.nan if case == "bad_scores" else 0.9]]),
                None,
            )

    ctx = context()
    with pytest.raises(ValueError):
        SAM2Segmenter(Invalid()).segment(Image.new("RGB", (320, 240)), [box(ctx)], (ctx, None))


def test_embedding_preprocessing_batching_shape_and_norm():
    ctx = context()
    image = Image.new("RGB", (320, 240), "red")
    boxes = [box(ctx) for _ in range(3)]
    masks = SAM2Segmenter(PredictorStub()).segment(image, boxes, (ctx, None))
    batches = []

    def forward(array):
        assert array.shape[1:] == (3, 224, 224) and array.dtype == np.float32
        assert np.isfinite(array).all()
        batches.append(len(array))
        return np.full((len(array), 384), 2, dtype=np.float32)

    adapter = DINOv2Embedder(forward, VisionSettings(_env_file=None, embedding_batch_size=2))
    results = adapter.embed(image, masks, boxes, (ctx, None))
    assert batches == [2, 1]
    assert [e.detection_id for e in results] == [b.id for b in boxes]
    assert all(e.dimension == 384 and abs(np.linalg.norm(e.values) - 1) < 1e-5 for e in results)
    assert adapter.embed(image, [], [], (ctx, None)) == []
    crop = prepare_crop(image, masks[0], boxes[0], 0.1)
    # Gray padding uses ImageNet normalization; central red content is retained.
    assert crop[0, 112, 112] > 2
    assert crop[1, 112, 112] < -1


@pytest.mark.parametrize("case", ["zero", "nan", "dimension", "alignment"])
def test_embedding_rejects_invalid_upstream_vectors(case):
    ctx = context()
    image = Image.new("RGB", (320, 240))
    boxes = [box(ctx)]
    masks = SAM2Segmenter(PredictorStub()).segment(image, boxes, (ctx, None))
    dimension = 3 if case == "dimension" else 384
    value = np.nan if case == "nan" else 0
    adapter = DINOv2Embedder(
        lambda _: np.full((1, dimension), value), VisionSettings(_env_file=None)
    )
    with pytest.raises(ValueError):
        adapter.embed(image, [] if case == "alignment" else masks, boxes, (ctx, None))


def test_real_contracts_flow_through_persistence_with_stubbed_upstream(tmp_path):
    import io
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from scene_tracker.application.ingest import ImageUpload, ingest_capture
    from scene_tracker.application.vision_pipeline import process_pipeline
    from scene_tracker.domain.enums import CameraID
    from scene_tracker.infrastructure.storage.local import LocalStore
    from scene_tracker.vision.contracts import ProcessingManifest

    env, run_id = uuid4(), uuid4()
    store = LocalStore(tmp_path, env)
    image = Image.new("RGB", (320, 240), "red")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    capture = ingest_capture(
        env,
        datetime.now(UTC),
        [ImageUpload(c, f"{c}.png", "image/png", stream.getvalue()) for c in CameraID],
        store,
    )
    settings = VisionSettings(_env_file=None)
    detector = GroundingDINO(
        lambda *args: (np.array([[0.5, 0.5, 0.5, 0.5]]), np.array([0.9]), ["chair"]), settings
    )
    predictor = PredictorStub()
    saved = {"detections": [], "artifacts": [], "manifest": None}
    repository = SimpleNamespace(
        add_artifact=lambda env, run, ref: saved["artifacts"].append(ref),
        add_detections=lambda rows: saved["detections"].extend(rows),
        progress=lambda *args: None,
        save_manifest=lambda run, manifest: saved.update(manifest=manifest),
    )
    config = {"provider": "real", "prompts": ["chair"], "vision": settings.model_dump(mode="json")}
    result = process_pipeline(
        repository,
        {"id": run_id, "config_hash": "0" * 64, "model_manifest": {"config": config}},
        capture.model_dump(),
        store,
        detector=detector,
        segmenter=SAM2Segmenter(predictor),
        embedder=DINOv2Embedder(lambda batch: np.ones((len(batch), 384)), settings),
        model_provenance={"validation": "stubbed upstream contract test; no pretrained inference"},
    )
    assert result.provider == "real" and result.scope == "real_vision_pipeline"
    assert predictor.encodings == 4
    assert len(saved["detections"]) == 4
    assert all(row["embedding_metadata"]["synthetic"] is False for row in saved["detections"])
    assert ProcessingManifest.model_validate(saved["manifest"]).run_id == run_id
    assert len([ref for ref in saved["artifacts"] if ref.kind == "detector_candidates"]) == 4


def test_empty_phrases_and_degenerate_boxes_remain_diagnostic():
    adapter = GroundingDINO(
        lambda *args: (
            np.array([[0.5, 0.5, 0.5, 0.5], [0.5, 0.5, 0, 0]]),
            np.array([0.1, 0.9]),
            ["", "chair"],
        ),
        VisionSettings(_env_file=None),
    )
    assert adapter.detect(None, ["chair"], (context(), None)) == []
    assert [c["decision"] for c in adapter.last_candidates] == ["empty_phrase", "degenerate_box"]

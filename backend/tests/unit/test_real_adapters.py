from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from scene_tracker.core.vision_settings import VisionSettings
from scene_tracker.vision.contracts import DetectionBox, FrameContext
from scene_tracker.vision.embeddings.dinov2 import DINOv2Embedder, prepare_crop
from scene_tracker.vision.segmentation.fake import FakeSegmenter


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


def test_embedding_preprocessing_batching_shape_and_norm():
    ctx = context()
    image = Image.new("RGB", (320, 240), "red")
    boxes = [box(ctx) for _ in range(3)]
    masks = FakeSegmenter().segment(image, boxes, (ctx, None))
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
    masks = FakeSegmenter().segment(image, boxes, (ctx, None))
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

    class ExtractorStub:
        def __init__(self):
            self.calls = 0
            self.last_candidates = []

        def extract(self, image, config):
            self.calls += 1
            ctx, _ = config
            boxes = [box(ctx)]
            return boxes, FakeSegmenter().segment(image, boxes, config)

    extractor = ExtractorStub()
    saved = {"detections": [], "artifacts": [], "manifest": None}
    repository = SimpleNamespace(
        add_artifact=lambda env, run, ref: saved["artifacts"].append(ref),
        add_detections=lambda rows: saved["detections"].extend(rows),
        progress=lambda *args: None,
        save_manifest=lambda run, manifest: saved.update(manifest=manifest),
    )
    config = {"provider": "real", "vision": settings.model_dump(mode="json")}
    result = process_pipeline(
        repository,
        {"id": run_id, "config_hash": "0" * 64, "model_manifest": {"config": config}},
        capture.model_dump(),
        store,
        extractor=extractor,
        embedder=DINOv2Embedder(lambda batch: np.ones((len(batch), 384)), settings),
        model_provenance={"validation": "stubbed upstream contract test; no pretrained inference"},
    )
    assert result.provider == "real" and result.scope == "real_vision_pipeline"
    assert extractor.calls == 4
    assert len(saved["detections"]) == 4
    assert all(row["embedding_metadata"]["synthetic"] is False for row in saved["detections"])
    assert ProcessingManifest.model_validate(saved["manifest"]).run_id == run_id
    assert len([ref for ref in saved["artifacts"] if ref.kind == "extractor_diagnostics"]) == 4

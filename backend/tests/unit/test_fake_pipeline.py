import io
import json
import zipfile
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

from scene_tracker.application.ingest import ImageUpload, ingest_capture
from scene_tracker.application.vision_pipeline import PipelineFailed, process_fake
from scene_tracker.domain.contracts import Mask
from scene_tracker.domain.enums import CameraID
from scene_tracker.infrastructure.storage.local import LocalStore
from scene_tracker.vision.contracts import PerCameraResult
from scene_tracker.vision.detection.fake import FakeDetector
from scene_tracker.vision.fixtures import METADATA_KEY, generate_capture, synthetic_image
from scene_tracker.vision.masks import decode_mask, encode_mask


class RecordingRepository:
    def __init__(self):
        self.artifacts, self.detections, self.manifests, self.updates = [], [], {}, []

    def add_artifact(self, environment_id, run_id, ref):
        self.artifacts.append(ref)

    def add_detections(self, records):
        self.detections.extend(records)

    def save_manifest(self, run_id, manifest):
        self.manifests[run_id] = manifest

    def progress(self, run_id, value):
        self.updates.append(value)


def setup_capture(tmp_path, *, empty=False):
    env = uuid4()
    store = LocalStore(tmp_path, env)
    capture = ingest_capture(
        env,
        datetime.now(UTC),
        [
            ImageUpload(c, f"{c}.png", "image/png", synthetic_image(c, empty=empty))
            for c in CameraID
        ],
        store,
    )
    run = {
        "id": uuid4(),
        "config_hash": "a" * 64,
        "model_manifest": {"config": {"provider": "fake", "preset": "fake-fixture"}},
    }
    return store, capture.model_dump(), run


@pytest.mark.parametrize("kind", ["zeros", "ones", "random", "thin"])
def test_rle_roundtrip(kind):
    array = np.zeros((17, 23), dtype=np.uint8)
    if kind == "ones":
        array[:] = 1
    elif kind == "random":
        array = np.random.default_rng(42).integers(0, 2, size=array.shape, dtype=np.uint8)
    elif kind == "thin":
        array[::2, 1] = 1
    rle = encode_mask(array)
    assert isinstance(rle.counts, str)
    assert np.array_equal(decode_mask(Mask.model_validate_json(rle.model_dump_json())), array)


def test_invalid_rle_and_nonbinary_masks():
    with pytest.raises(ValueError):
        decode_mask(Mask(size=(4, 4), counts="!"))
    with pytest.raises(ValueError):
        encode_mask([[0, 2]])


def test_fixture_generator_four_labeled_images(tmp_path):
    generate_capture(tmp_path)
    for camera in CameraID:
        with Image.open(tmp_path / f"{camera}.png") as image:
            assert image.size == (320, 240)
            scenario = json.loads(image.info[METADATA_KEY])
            assert scenario["camera_id"] == camera
            assert len(scenario["objects"]) == 2
    with pytest.raises(FileExistsError):
        generate_capture(tmp_path)


@pytest.mark.parametrize("empty", [False, True])
def test_fake_contracts_masks_vectors_and_debug_bundle(tmp_path, empty):
    store, capture, run = setup_capture(tmp_path, empty=empty)
    repository = RecordingRepository()
    manifest = process_fake(repository, run, capture, store)
    assert len(manifest.cameras) == 4
    assert len(repository.detections) == (0 if empty else 8)
    assert manifest.inference_performed is False
    assert [c.camera_id for c in manifest.cameras] == list(CameraID)
    for camera in manifest.cameras:
        assert PerCameraResult.model_validate_json(camera.model_dump_json()) == camera
        for box, mask, embedding in zip(
            camera.detections, camera.masks, camera.embeddings, strict=True
        ):
            assert box.id == mask.detection_id == embedding.detection_id
            array = decode_mask(mask.rle)
            x1, y1, x2, y2 = box.box_xyxy
            assert int(array.sum()) == (x2 - x1) * (y2 - y1)
            assert array[y1:y2, x1:x2].all()
            assert embedding.dimension == 8
            assert abs(np.linalg.norm(embedding.values) - 1) < 1e-5
    bundle_ref = next(r for r in repository.artifacts if r.kind == "inspection_bundle")
    with zipfile.ZipFile(io.BytesIO(store.get(store.stat(bundle_ref.key)))) as archive:
        assert "debug/cam_04/boxes.png" in archive.namelist()
        assert "debug/cam_04/masks.png" in archive.namelist()
        html = archive.read("debug/summary.html").decode()
        assert "OVERHEAD" in html and "data:image/png;base64," in html
        assert "No pretrained inference" in html
        assert json.loads(archive.read("debug/temporal_matches.json"))["implemented"] is False
    assert repository.updates[-1]["completed_cameras"] == 4


def test_camera_fault_and_retry_preserve_old_artifacts(tmp_path):
    store, capture, run = setup_capture(tmp_path)
    repository = RecordingRepository()

    class FaultyDetector(FakeDetector):
        def detect(self, image, prompts, config):
            if config[0].camera_id == CameraID.CAM_02:
                raise RuntimeError("injected camera fault")
            return super().detect(image, prompts, config)

    with pytest.raises(PipelineFailed, match="cam_02"):
        process_fake(repository, run, capture, store, detector=FaultyDetector())
    assert [r["status"] for r in repository.manifests[run["id"]]["cameras"]] == [
        "succeeded",
        "failed",
        "succeeded",
        "succeeded",
    ]
    old = {r.key: store.get(store.stat(r.key)) for r in repository.artifacts}
    retry = run | {"id": uuid4()}
    process_fake(repository, retry, capture, store)
    for key, data in old.items():
        assert store.get(store.stat(key)) == data
    assert len(repository.manifests) == 2


def test_repeatable_boxes_masks_embeddings_and_overlays(tmp_path):
    store, capture, run = setup_capture(tmp_path / "first")
    first = RecordingRepository()
    process_fake(first, run, capture, store)
    # Repeat with identical IDs in another test store; timing changes must not mask content drift.
    other = LocalStore(tmp_path / "second", capture["environment_id"])
    for frame in capture["frames"]:
        blob = store.stat(frame["storage_key"])
        other.put(blob.key, store.get(blob), blob.content_type)
    second = RecordingRepository()
    process_fake(second, run, capture, other)
    for ref in first.artifacts:
        if ref.kind not in {"manifest", "report", "inspection_bundle"}:
            assert store.get(store.stat(ref.key)) == other.get(other.stat(ref.key))


def test_rejects_adapter_alignment_and_records_diagnostics(tmp_path):
    from scene_tracker.vision.segmentation.fake import FakeSegmenter

    store, capture, run = setup_capture(tmp_path)
    repository = RecordingRepository()

    class Misaligned(FakeSegmenter):
        def segment(self, image, boxes, config):
            return list(reversed(super().segment(image, boxes, config)))

    with pytest.raises(PipelineFailed, match="alignment mismatch"):
        process_fake(repository, run, capture, store, segmenter=Misaligned())
    assert all(c["status"] == "failed" for c in repository.manifests[run["id"]]["cameras"])
    assert not repository.detections
    assert any(a.kind == "report" for a in repository.artifacts)

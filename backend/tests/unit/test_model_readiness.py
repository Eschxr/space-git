import subprocess
import sys
from pathlib import Path

import pytest

from scene_tracker.core.model_pins import PINS
from scene_tracker.core.vision_settings import VisionSettings
from scene_tracker.vision.readiness import (
    ModelUnavailable,
    directory_hash,
    preflight,
    sha256_file,
    verify_source,
)


def assets(tmp_path):
    values = {}
    for name, prefix in [("groundingdino", "grounding"), ("sam2", "sam2"), ("dinov2", "dinov2")]:
        checkpoint = tmp_path / f"{name}.weights"
        checkpoint.write_bytes(b"stub assets for hash tests, not model weights")
        source = tmp_path / name
        source.mkdir()
        values[prefix + "_checkpoint"] = checkpoint
        values[prefix + "_sha256"] = sha256_file(checkpoint)
        values[prefix + "_source_dir"] = source
    for prefix, filename in [
        ("grounding", "groundingdino/config/GroundingDINO_SwinT_OGC.py"),
        ("sam2", "sam2/configs/sam2.1/sam2.1_hiera_s.yaml"),
    ]:
        path = values[prefix + "_source_dir"] / filename
        path.parent.mkdir(parents=True)
        path.write_text("stub config, never executed")
    bert = tmp_path / "bert"
    bert.mkdir()
    for name in ["config.json", "vocab.txt", "tokenizer_config.json", "model.safetensors"]:
        (bert / name).write_bytes(b"stub asset")
    return VisionSettings(_env_file=None, **values, bert_dir=bert, bert_sha256=directory_hash(bert))


def test_file_readiness_hashes_and_snapshot(tmp_path):
    settings = assets(tmp_path)
    seen = []

    def verifier(path, pin):
        seen.append(pin)
        return str(path.resolve())

    result = preflight(settings, source_verifier=verifier)
    assert result["status"] == "files_verified_runtime_unprobed"
    assert set(seen) == set(PINS.values())
    assert Path(result["checkpoints"]["sam2"]["path"]).is_absolute()
    settings.sam2_checkpoint.write_bytes(b"corrupted")
    with pytest.raises(ModelUnavailable, match="SHA-256 mismatch"):
        preflight(settings, source_verifier=verifier)


def test_missing_assets_and_source_pin_fail_clearly(tmp_path):
    with pytest.raises(ModelUnavailable, match="missing groundingdino checkpoint"):
        preflight(VisionSettings(_env_file=None, grounding_checkpoint=None))
    with pytest.raises(ModelUnavailable):
        verify_source(tmp_path, "0" * 40)
    settings = assets(tmp_path)
    (settings.bert_dir / "vocab.txt").unlink()
    with pytest.raises(ModelUnavailable, match="BERT"):
        preflight(settings, source_verifier=lambda path, _: str(path.resolve()))


@pytest.mark.parametrize("command", ["model-readiness", "model-smoke"])
def test_cli_missing_weights_is_actionable_and_offline(tmp_path, command):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; os.environ['VISION_GROUNDING_CHECKPOINT']='/missing/model.pth'; "
                "from scene_tracker.cli import main; main()"
            ),
            command,
            *(
                ["--input", str(tmp_path), "--output", str(tmp_path / "smoke")]
                if command == "model-smoke"
                else []
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "model_unavailable" in result.stderr
    assert "docs/model-setup.md" in result.stderr


def test_real_pipeline_cannot_use_fake_defaults(tmp_path):
    from scene_tracker.application.vision_pipeline import process_pipeline
    from scene_tracker.vision.runtime import load_models

    with pytest.raises(RuntimeError, match="fake fallback is forbidden"):
        process_pipeline(None, {"model_manifest": {"config": {"provider": "real"}}}, None, None)
    with pytest.raises(ModelUnavailable):
        load_models(VisionSettings(_env_file=None, grounding_checkpoint=None))


def test_settings_snapshot_preserves_model_cache_and_rejects_bad_prompts(tmp_path):
    settings = VisionSettings(_env_file=None, model_cache_dir=tmp_path)
    assert (
        VisionSettings.model_validate(settings.model_dump(mode="json")).model_cache_dir == tmp_path
    )
    with pytest.raises(ValueError):
        VisionSettings(_env_file=None, prompts=("",))

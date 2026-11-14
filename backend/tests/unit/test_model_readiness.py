import subprocess
import sys

import pytest

from scene_tracker.core.vision_settings import VisionSettings
from scene_tracker.vision.readiness import ModelUnavailable


@pytest.mark.parametrize("command", ["model-readiness", "model-smoke"])
def test_cli_missing_weights_is_actionable_and_offline(tmp_path, command):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; os.environ['YOLOE_CHECKPOINT']='/missing/model.pth'; "
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
        load_models(
            __import__(
                "scene_tracker.core.vision_settings", fromlist=["VisionSettings"]
            ).VisionSettings(_env_file=None, yoloe_checkpoint=None)
        )


def test_settings_snapshot_preserves_model_cache_and_rejects_wrong_extractor(tmp_path):
    settings = VisionSettings(_env_file=None, model_cache_dir=tmp_path)
    assert (
        VisionSettings.model_validate(settings.model_dump(mode="json")).model_cache_dir == tmp_path
    )
    with pytest.raises(ValueError):
        VisionSettings(_env_file=None, extractor="groundingdino")


def test_source_verification_rejects_missing_or_unpinned_checkout(tmp_path):
    from scene_tracker.vision.assets import verify_source

    with pytest.raises(ModelUnavailable, match="missing pinned"):
        verify_source(tmp_path / "missing", "0" * 40)
    with pytest.raises(ModelUnavailable, match="clean checkout"):
        verify_source(tmp_path, "0" * 40)

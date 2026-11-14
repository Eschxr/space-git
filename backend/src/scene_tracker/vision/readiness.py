"""CPU-only local asset verification; no Ultralytics/Torch imports or downloads."""

from pathlib import Path

from scene_tracker.core.model_pins import PINS
from scene_tracker.vision.assets import ModelUnavailable, sha256_file, verify_source

ULTRALYTICS_VERSION = "8.4.0"


def preflight(settings, source_verifier=verify_source):
    try:
        if settings.extractor != "yoloe":
            raise ModelUnavailable("real mode requires VISION_EXTRACTOR=yoloe")
        checkpoints = {}
        for name, path, expected in [
            ("yoloe", settings.yoloe_checkpoint, settings.yoloe_sha256),
            ("dinov2", settings.dinov2_checkpoint, settings.dinov2_sha256),
        ]:
            if path is None or not path.is_file() or expected is None:
                raise ModelUnavailable(f"missing {name} checkpoint or expected SHA-256")
            if name == "yoloe" and path.name != "yoloe-11s-seg-pf.pt":
                raise ModelUnavailable("expected prompt-free yoloe-11s-seg-pf.pt")
            actual = sha256_file(path)
            if actual != expected:
                raise ModelUnavailable(f"{name} checkpoint SHA-256 mismatch")
            checkpoints[name] = {"path": str(path.resolve()), "sha256": actual}
        source = source_verifier(settings.dinov2_source_dir, PINS["dinov2"])
        return {
            "checkpoints": checkpoints,
            "sources": {"dinov2": {"path": str(Path(source).resolve()), "commit": PINS["dinov2"]}},
            "ultralytics": ULTRALYTICS_VERSION,
            "device": settings.yoloe_device,
            "embedding_device": settings.device,
            "status": "files_verified_runtime_unprobed",
        }
    except ModelUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise ModelUnavailable(str(exc)) from exc

"""Readiness preflight uses only standard library code and local operator assets."""

import hashlib
import json
import subprocess
from pathlib import Path

from scene_tracker.core.errors import AppError
from scene_tracker.core.model_pins import PINS


class ModelUnavailable(AppError):
    def __init__(self, message):
        super().__init__("model_unavailable", message + "; see docs/model-setup.md", 503)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_hash(path):
    files = {
        str(f.relative_to(path)): sha256_file(f)
        for f in sorted(Path(path).rglob("*"))
        if f.is_file()
    }
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def verify_source(path, expected):
    if path is None or not Path(path).is_dir():
        raise ModelUnavailable("missing pinned source checkout")
    path = Path(path).resolve()
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    dirty = subprocess.run(
        ["git", "-C", str(path), "diff", "--quiet", "HEAD", "--"], capture_output=True, check=False
    )
    if result.returncode or result.stdout.strip() != expected or dirty.returncode:
        raise ModelUnavailable(f"source {path} must be a clean checkout at {expected}")
    return str(path)


def preflight(settings, source_verifier=verify_source):
    try:
        return _preflight(settings, source_verifier)
    except ModelUnavailable:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ModelUnavailable(f"unable to verify local assets: {exc}") from exc


def _preflight(settings, source_verifier):
    checkpoints, sources = {}, {}
    names = (("groundingdino", "grounding"), ("sam2", "sam2"), ("dinov2", "dinov2"))
    for name, prefix in names:
        path = getattr(settings, prefix + "_checkpoint")
        expected = getattr(settings, prefix + "_sha256")
        if path is None or not Path(path).is_file() or expected is None:
            raise ModelUnavailable(f"missing {name} checkpoint or expected SHA-256")
        actual = sha256_file(path)
        if actual != expected:
            raise ModelUnavailable(f"{name} checkpoint SHA-256 mismatch")
        checkpoints[name] = {"path": str(Path(path).resolve()), "sha256": actual}
        source = source_verifier(getattr(settings, prefix + "_source_dir"), PINS[name])
        sources[name] = {"path": source, "commit": PINS[name]}
    bert = settings.bert_dir
    if bert is None or not all(
        (bert / f).is_file() for f in ["config.json", "vocab.txt", "tokenizer_config.json"]
    ):
        raise ModelUnavailable("missing local BERT tokenizer/config assets")
    if not any((bert / f).is_file() for f in ["model.safetensors", "pytorch_model.bin"]):
        raise ModelUnavailable("missing local BERT encoder weights")
    bert_hash = directory_hash(bert)
    if not settings.bert_sha256 or bert_hash != settings.bert_sha256:
        raise ModelUnavailable("BERT directory SHA-256 mismatch or missing expected hash")
    grounding_config = (
        Path(sources["groundingdino"]["path"]) / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
    )
    sam_config = Path(sources["sam2"]["path"]) / "sam2/configs/sam2.1/sam2.1_hiera_s.yaml"
    for config in [grounding_config, sam_config]:
        if not config.is_file():
            raise ModelUnavailable(f"missing pinned configuration {config}")
    return {
        "checkpoints": checkpoints,
        "sources": sources,
        "bert": {"path": str(bert.resolve()), "sha256": bert_hash},
        "configs": {
            "groundingdino": sha256_file(grounding_config),
            "sam2": sha256_file(sam_config),
        },
        "device": settings.device,
        "status": "files_verified_runtime_unprobed",
    }

"""CPU-only local asset hashes and pinned source checks. No model imports."""

import hashlib
import subprocess
from pathlib import Path

from scene_tracker.core.errors import AppError


class ModelUnavailable(AppError):
    def __init__(self, message):
        super().__init__("model_unavailable", message + "; see docs/model-setup.md", 503)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

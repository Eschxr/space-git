import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID


class StorageError(ValueError):
    pass


@dataclass(frozen=True)
class Blob:
    key: str
    sha256: str
    content_type: str
    size: int


ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/json",
    "application/octet-stream",
    "application/x-ply",
    "text/html",
    "application/zip",
}


def validate(key: str, content_type: str) -> None:
    if (
        not key
        or key.startswith("/")
        or "\\" in key
        or any(p in {"", ".", ".."} for p in key.split("/"))
        or str(PurePosixPath(key)) != key
    ):
        raise StorageError("unsafe storage key")
    if content_type not in ALLOWED_TYPES:
        raise StorageError("unsupported content type")


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scoped_key(environment_id: UUID, key: str) -> str:
    validate(key, "application/octet-stream")
    parts = key.split("/")
    if parts[0] == "originals":
        if len(parts) < 3 or parts[1] != str(environment_id):
            raise StorageError("original key belongs to another environment")
        return key
    return f"environments/{environment_id}/{key}"


class ArtifactStore(Protocol):
    def stat(self, key: str) -> Blob: ...
    def put(self, key: str, data: bytes, content_type: str) -> Blob: ...
    def get(self, blob: Blob) -> bytes: ...
    def presign(self, blob: Blob, expires_seconds: int = 300) -> str: ...

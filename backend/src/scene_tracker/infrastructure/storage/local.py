import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from scene_tracker.infrastructure.storage.base import (
    Blob,
    StorageError,
    checksum,
    scoped_key,
    validate,
)


class LocalStore:
    """Private local test store. Publish complete immutable blobs using hard links."""

    def __init__(self, root: Path, environment_id: UUID):
        self.root = root.resolve()
        self.environment_id = environment_id

    def _path(self, key: str) -> Path:
        path = self.root / scoped_key(self.environment_id, key)
        if not path.resolve().is_relative_to(self.root):
            raise StorageError("path escapes storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> Blob:
        validate(key, content_type)
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = Blob(key, checksum(data), content_type, len(data))
        # Store metadata and bytes as one atomic file, so concurrent puts cannot tear metadata.
        header = json.dumps(blob.__dict__).encode() + b"\n"
        temp = target.parent / f".{uuid4()}.tmp"
        try:
            with temp.open("xb") as stream:
                stream.write(header + data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp, target)
            except FileExistsError:
                if self.get(blob) != data:
                    raise StorageError("immutable key conflict") from None
        finally:
            temp.unlink(missing_ok=True)
        return blob

    def stat(self, key: str) -> Blob:
        with self._path(key).open("rb") as stream:
            blob = Blob(**json.loads(stream.readline()))
        if blob.key != key:
            raise StorageError("blob key mismatch")
        return blob

    def get(self, blob: Blob) -> bytes:
        validate(blob.key, blob.content_type)
        with self._path(blob.key).open("rb") as stream:
            stored = Blob(**json.loads(stream.readline()))
            data = stream.read()
        if stored != blob or checksum(data) != blob.sha256 or len(data) != blob.size:
            raise StorageError("blob metadata/checksum mismatch")
        return data

    def presign(self, blob: Blob, expires_seconds: int = 300) -> str:
        raise NotImplementedError("LocalStore has no HTTP server; use get(), not a fake signed URL")

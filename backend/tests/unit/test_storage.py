from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

from scene_tracker.infrastructure.storage.base import StorageError
from scene_tracker.infrastructure.storage.local import LocalStore


def test_immutable_checksum_and_scope(tmp_path):
    store = LocalStore(tmp_path, uuid4())
    blob = store.put("vision/run/result.json", b"{}", "application/json")
    assert store.put(blob.key, b"{}", blob.content_type) == blob
    with pytest.raises(StorageError):
        store.put(blob.key, b"different", blob.content_type)
    with pytest.raises(StorageError):
        store.put(blob.key, b"{}", "image/png")
    with pytest.raises(StorageError):
        store.get(replace(blob, sha256="0" * 64))
    with pytest.raises(FileNotFoundError):
        LocalStore(tmp_path, uuid4()).get(blob)
    with pytest.raises(StorageError):
        store.put(f"originals/{uuid4()}/capture/x.png", b"x", "image/png")
    with pytest.raises(NotImplementedError):
        store.presign(blob)


@pytest.mark.parametrize("key", ["../x", "/x", "a//b", "a/./b", "a/../b", "a\\b"])
def test_unsafe_keys(tmp_path, key):
    with pytest.raises(StorageError):
        LocalStore(tmp_path, uuid4()).put(key, b"x", "application/json")


def test_unknown_content_type(tmp_path):
    with pytest.raises(StorageError):
        LocalStore(tmp_path, uuid4()).put("x", b"x", "text/unknown")


def test_atomic_concurrent_put(tmp_path):
    store = LocalStore(tmp_path, uuid4())

    def write(data):
        try:
            return store.put("result", data, "application/octet-stream")
        except StorageError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, [b"first", b"second"]))
    assert sum(r is not None for r in results) == 1
    winner = next(r for r in results if r)
    assert store.get(winner) in {b"first", b"second"}


def test_detects_stored_byte_corruption(tmp_path):
    store = LocalStore(tmp_path, uuid4())
    blob = store.put("result", b"original", "application/octet-stream")
    path = store._path(blob.key)
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + b"x")
    with pytest.raises(StorageError, match="checksum"):
        store.get(blob)

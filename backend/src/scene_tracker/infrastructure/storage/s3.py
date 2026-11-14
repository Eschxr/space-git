from datetime import timedelta
from uuid import UUID

from minio import Minio
from minio.error import S3Error

from scene_tracker.infrastructure.storage.base import (
    Blob,
    StorageError,
    checksum,
    scoped_key,
    validate,
)


class S3Store:
    """Uses conditional single PUTs, never a check-then-write overwrite."""

    def __init__(
        self, client: Minio, bucket: str, environment_id: UUID, public_client: Minio | None = None
    ):
        self.client = client
        self.public_client = public_client or client
        self.bucket = bucket
        self.environment_id = environment_id

    def put(self, key: str, data: bytes, content_type: str) -> Blob:
        validate(key, content_type)
        full_key = scoped_key(self.environment_id, key)
        blob = Blob(key, checksum(data), content_type, len(data))
        # MinIO's high-level put_object lacks conditional-write headers. Its low-level
        # request signs this S3 PutObject request, including If-None-Match.
        try:
            self.client._execute(
                "PUT",
                self.bucket,
                full_key,
                body=data,
                headers={
                    "Content-Type": content_type,
                    "If-None-Match": "*",
                    "x-amz-meta-sha256": blob.sha256,
                },
            )
        except S3Error as exc:
            if exc.code not in {"PreconditionFailed", "ConditionalRequestConflict"}:
                raise
            self.get(blob)  # Idempotent only if content AND metadata agree.
        return blob

    def stat(self, key: str) -> Blob:
        result = self.client.stat_object(self.bucket, scoped_key(self.environment_id, key))
        return Blob(
            key, result.metadata.get("x-amz-meta-sha256", ""), result.content_type, result.size
        )

    def get(self, blob: Blob) -> bytes:
        validate(blob.key, blob.content_type)
        key = scoped_key(self.environment_id, blob.key)
        response = self.client.get_object(self.bucket, key)
        try:
            data = response.read()
            if (
                response.headers.get("Content-Type") != blob.content_type
                or response.headers.get("x-amz-meta-sha256") != blob.sha256
                or checksum(data) != blob.sha256
                or len(data) != blob.size
            ):
                raise StorageError("blob metadata/checksum mismatch")
            return data
        finally:
            response.close()
            response.release_conn()

    def presign(self, blob: Blob, expires_seconds: int = 300) -> str:
        validate(blob.key, blob.content_type)
        if not 1 <= expires_seconds <= 3600:
            raise StorageError("URL expiry must be between 1 and 3600 seconds")
        return self.public_client.presigned_get_object(
            self.bucket,
            scoped_key(self.environment_id, blob.key),
            expires=timedelta(seconds=expires_seconds),
        )

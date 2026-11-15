from minio import Minio

from scene_tracker.infrastructure.storage.s3 import S3Store


def s3_store_factory(settings):
    client = Minio(
        settings.s3_endpoint,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        secure=settings.s3_secure,
        region=settings.s3_region,
    )
    public = Minio(
        settings.public_objectstore_endpoint,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        secure=settings.s3_secure,
        region=settings.s3_region,
    )
    return lambda env: S3Store(client, settings.s3_bucket, env, public)

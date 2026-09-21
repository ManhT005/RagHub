from io import BytesIO
from urllib.parse import urlsplit

from minio import Minio

from app.core.config import Settings, get_settings


class MinioObjectStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        parsed = urlsplit(self.settings.s3_endpoint)
        endpoint = parsed.netloc or parsed.path
        self.client = Minio(
            endpoint,
            access_key=self.settings.s3_access_key,
            secret_key=self.settings.s3_secret_key,
            secure=self.settings.s3_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.settings.s3_bucket):
            self.client.make_bucket(self.settings.s3_bucket)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.ensure_bucket()
        self.client.put_object(
            self.settings.s3_bucket,
            key,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.settings.s3_bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def remove(self, key: str) -> None:
        self.client.remove_object(self.settings.s3_bucket, key)

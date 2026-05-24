import uuid
import logging

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """
    S3-compatible storage abstraction backed by MinIO (local) or
    Linode Object Storage (production).

    Only presigned URLs are returned to callers — raw credentials are
    never exposed through the API.
    """

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            region_name=settings.STORAGE_REGION,
            # Required for path-style URLs used by MinIO
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._bucket = settings.STORAGE_BUCKET
        self._expiry = settings.PRESIGNED_URL_EXPIRY
        self._ensure_bucket()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_upload_url(self, storage_key: str, content_type: str) -> str:
        """Return a presigned PUT URL valid for *expiry* seconds."""
        try:
            url = self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": storage_key,
                    "ContentType": content_type,
                },
                ExpiresIn=self._expiry,
            )
            return url
        except ClientError as exc:
            logger.error("Failed to generate upload URL for key=%s: %s", storage_key, exc)
            raise

    def generate_download_url(self, storage_key: str) -> str:
        """Return a presigned GET URL valid for *expiry* seconds."""
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": storage_key},
                ExpiresIn=self._expiry,
            )
            return url
        except ClientError as exc:
            logger.error("Failed to generate download URL for key=%s: %s", storage_key, exc)
            raise

    def upload_file(self, storage_key: str, data: bytes, content_type: str) -> None:
        """Upload bytes directly to the bucket (server-side, no presigned URL needed)."""
        try:
            import io
            self._client.upload_fileobj(
                io.BytesIO(data),
                self._bucket,
                storage_key,
                ExtraArgs={"ContentType": content_type},
            )
        except ClientError as exc:
            logger.error("Failed to upload file key=%s: %s", storage_key, exc)
            raise

    def fetch_object(self, storage_key: str) -> bytes:
        """Download and return the raw bytes for *storage_key*."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=storage_key)
            return response["Body"].read()
        except ClientError as exc:
            logger.error("Failed to fetch object key=%s: %s", storage_key, exc)
            raise

    @staticmethod
    def build_storage_key(project_name: str, run_identifier: str, test_name: str, file_name: str) -> str:
        """
        Produce a deterministic, collision-resistant key.

        Pattern: <project>/<run>/<test>/<uuid>-<file_name>
        """
        unique = uuid.uuid4().hex[:8]
        # Sanitise path segments to avoid directory traversal
        parts = [
            _safe_segment(project_name),
            _safe_segment(run_identifier),
            _safe_segment(test_name),
            f"{unique}-{_safe_segment(file_name)}",
        ]
        return "/".join(parts)

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects whose key starts with *prefix*."""
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                self._client.delete_objects(
                    Bucket=self._bucket, Delete={"Objects": objects, "Quiet": True}
                )

    def delete_objects(self, keys: list[str]) -> None:
        """Delete a specific list of objects by their storage keys."""
        if not keys:
            return
        objects = [{"Key": k} for k in keys]
        self._client.delete_objects(
            Bucket=self._bucket, Delete={"Objects": objects, "Quiet": True}
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=self._bucket)
                logger.info("Created bucket: %s", self._bucket)
            else:
                logger.error("Unexpected error checking bucket: %s", exc)
                raise


def _safe_segment(value: str) -> str:
    """Strip characters that could be used for path traversal or injection."""
    import re
    return re.sub(r"[^a-zA-Z0-9._\-]", "_", value)


# Module-level singleton — instantiated lazily on first import of this module.
storage_service = StorageService()

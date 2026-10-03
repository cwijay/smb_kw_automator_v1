"""Object storage behind one small interface. Keys always start with the org UUID, never a name."""

import asyncio
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from keel.platform.config import get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...


class LocalStorage:
    """Filesystem storage for local development. Swap for an S3/R2 implementation in the cloud."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("storage key escapes the storage root")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class S3Storage:
    """S3-compatible object storage (Cloudflare R2, MinIO, S3). Credentials come from the standard
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY environment variables, never from config files."""

    def __init__(self, bucket: str, endpoint_url: str | None, region: str, client: Any = None) -> None:
        if client is None:
            import boto3  # optional extra: `uv sync --extra cloud`

            client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.bucket, self.client = bucket, client

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data)

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)


def doc_key(org_id: uuid.UUID, doc_id: uuid.UUID, name: str) -> str:
    return f"{org_id}/docs/{doc_id}/{name}"


@lru_cache
def _s3(bucket: str, endpoint_url: str | None, region: str) -> S3Storage:
    return S3Storage(bucket, endpoint_url, region)  # one client (and connection pool) per process


def storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        if not s.s3_bucket:
            raise RuntimeError("KEEL_S3_BUCKET is required when KEEL_STORAGE_BACKEND=s3.")
        return _s3(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
    return LocalStorage(s.storage_dir)

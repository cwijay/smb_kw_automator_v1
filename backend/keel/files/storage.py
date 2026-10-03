"""Object storage behind one small interface. Keys always start with the org UUID, never a name."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from keel.platform.config import get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...


class LocalStorage:
    """Filesystem storage for local development."""

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


TokenSource = Callable[[], Awaitable[str]]


class _AdcToken:
    """OAuth token from Application Default Credentials: the Cloud Run service account in the cloud,
    `gcloud auth application-default login` locally. No keys in config or in Secret Manager."""

    SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"

    def __init__(self) -> None:
        import google.auth

        self.creds, _ = google.auth.default(scopes=[self.SCOPE])
        self.lock = asyncio.Lock()

    def _refresh(self) -> None:
        from google.auth.transport.requests import Request

        self.creds.refresh(Request())  # type: ignore[no-untyped-call]  # google-auth is untyped here

    async def __call__(self) -> str:
        async with self.lock:
            if not self.creds.valid:  # google-auth treats tokens near expiry as invalid (refresh margin)
                await asyncio.to_thread(self._refresh)
            return str(self.creds.token)


class GCSStorage:
    """Google Cloud Storage over its JSON API with httpx: async, no extra SDK."""

    def __init__(
        self,
        bucket: str,
        endpoint: str = "https://storage.googleapis.com",
        token: TokenSource | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bucket, self.endpoint = bucket, endpoint.rstrip("/")
        self.token = token or _AdcToken()
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))

    async def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.token()}"}

    async def put(self, key: str, data: bytes) -> None:
        r = await self.client.post(
            f"{self.endpoint}/upload/storage/v1/b/{self.bucket}/o",
            params={"uploadType": "media", "name": key},
            headers=await self._headers() | {"Content-Type": "application/octet-stream"},
            content=data,
        )
        r.raise_for_status()

    async def get(self, key: str) -> bytes:
        r = await self.client.get(
            f"{self.endpoint}/storage/v1/b/{self.bucket}/o/{quote(key, safe='')}",
            params={"alt": "media"},
            headers=await self._headers(),
        )
        if r.status_code == 404:
            raise FileNotFoundError(key)
        r.raise_for_status()
        return r.content


def doc_key(org_id: uuid.UUID, doc_id: uuid.UUID, name: str) -> str:
    return f"{org_id}/docs/{doc_id}/{name}"


@lru_cache
def _gcs(bucket: str, endpoint: str) -> GCSStorage:
    return GCSStorage(bucket, endpoint)  # one HTTP client and token cache per process


def storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "gcs":
        if not s.gcs_bucket:
            raise RuntimeError("KEEL_GCS_BUCKET is required when KEEL_STORAGE_BACKEND=gcs.")
        return _gcs(s.gcs_bucket, s.gcs_endpoint)
    return LocalStorage(s.storage_dir)

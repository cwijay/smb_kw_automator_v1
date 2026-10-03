"""Object storage behind one small interface. Keys always start with the org UUID, never a name."""

import uuid
from pathlib import Path
from typing import Protocol

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


def doc_key(org_id: uuid.UUID, doc_id: uuid.UUID, name: str) -> str:
    return f"{org_id}/docs/{doc_id}/{name}"


def storage() -> Storage:
    return LocalStorage(get_settings().storage_dir)

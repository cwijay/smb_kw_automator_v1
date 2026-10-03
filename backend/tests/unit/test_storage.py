import uuid
from pathlib import Path

import httpx
import pytest

from keel.files.storage import GCSStorage, LocalStorage, doc_key


def _fake_gcs(log: list[httpx.Request]) -> httpx.MockTransport:
    objects: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        if request.url.path == "/upload/storage/v1/b/keel-files/o":
            objects[request.url.params["name"]] = request.content
            return httpx.Response(200, json={"name": request.url.params["name"]})
        prefix = "/storage/v1/b/keel-files/o/"
        if request.url.path.startswith(prefix) and request.url.params.get("alt") == "media":
            key = request.url.path.removeprefix(prefix)  # httpx decodes %2F back to /
            return httpx.Response(200, content=objects[key]) if key in objects else httpx.Response(404)
        return httpx.Response(400)

    return httpx.MockTransport(handler)


async def test_gcs_round_trip_with_service_account_token() -> None:
    log: list[httpx.Request] = []

    async def token() -> str:
        return "ya29.test"

    gcs = GCSStorage("keel-files", token=token, client=httpx.AsyncClient(transport=_fake_gcs(log)))
    key = doc_key(uuid.uuid4(), uuid.uuid4(), "original-order pad.pdf")
    await gcs.put(key, b"%PDF-1")
    assert await gcs.get(key) == b"%PDF-1"
    assert all(r.headers["authorization"] == "Bearer ya29.test" for r in log)
    assert "%2F" in str(log[1].url.raw_path)  # the object name is one path segment: slashes encoded
    with pytest.raises(FileNotFoundError):
        await gcs.get(doc_key(uuid.uuid4(), uuid.uuid4(), "missing.pdf"))


async def test_local_storage_refuses_keys_outside_the_root(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        await store.put("../../etc/passwd", b"x")

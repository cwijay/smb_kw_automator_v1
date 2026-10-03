import io
import uuid
from pathlib import Path

import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from keel.files.storage import LocalStorage, S3Storage, doc_key


async def test_s3_storage_round_trip() -> None:
    import boto3

    client = boto3.client("s3", region_name="auto", aws_access_key_id="x", aws_secret_access_key="y")
    key = doc_key(uuid.uuid4(), uuid.uuid4(), "original.pdf")
    with Stubber(client) as stub:
        stub.add_response("put_object", {}, {"Bucket": "keel", "Key": key, "Body": b"%PDF-1"})
        stub.add_response(
            "get_object", {"Body": StreamingBody(io.BytesIO(b"%PDF-1"), 6)}, {"Bucket": "keel", "Key": key}
        )
        s3 = S3Storage("keel", None, "auto", client=client)
        await s3.put(key, b"%PDF-1")
        assert await s3.get(key) == b"%PDF-1"
        stub.assert_no_pending_responses()


async def test_local_storage_refuses_keys_outside_the_root(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        await store.put("../../etc/passwd", b"x")

"""Unit tests for streaming backup uploads and downloads."""

import asyncio
import tracemalloc
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from custom_components.s3_compatible import backup as backup_module
from custom_components.s3_compatible.backup import S3BackupAgent, with_retries
from custom_components.s3_compatible.exceptions import ClientError
from custom_components.s3_compatible.exceptions import ConnectionError as S3ConnectionError
from custom_components.s3_compatible.s3rest import S3RestClient, _StreamingBody
from homeassistant.components.backup import AgentBackup, BackupAgentError
from requests.exceptions import Timeout as RequestsTimeout

MIB = 2**20


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    delays: list[float] = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(backup_module.asyncio, "sleep", fake_sleep)
    return delays


def client_error(status: int, headers: dict | None = None) -> ClientError:
    return ClientError(
        {"ResponseMetadata": {"HTTPStatusCode": status, "HTTPHeaders": headers or {}}},
        "Test",
    )


class FakeClient:
    def __init__(self) -> None:
        self.parts: dict[int, int] = {}
        self.part_types: set[type] = set()
        self.calls: list[str] = []
        self.put_bodies: dict[str, object] = {}
        self.create_errors: list[Exception] = []
        self.upload_part_errors: list[Exception] = []
        self.complete_errors: list[Exception] = []
        self.put_errors: dict[str, list[Exception]] = {}
        self.put_attempts: dict[str, int] = {}
        self.head_error: Exception | None = None
        self.download_chunks: list[bytes] = []

    async def create_multipart_upload(self, **kwargs):
        self.calls.append("create")
        if self.create_errors:
            raise self.create_errors.pop(0)
        return {"UploadId": "upload-1"}

    async def upload_part(self, *, PartNumber, Body, **kwargs):
        if self.upload_part_errors:
            raise self.upload_part_errors.pop(0)
        self.parts[PartNumber] = len(Body)
        self.part_types.add(type(Body))
        return {"ETag": f"etag-{PartNumber}"}

    async def complete_multipart_upload(self, **kwargs):
        self.calls.append("complete")
        if self.complete_errors:
            raise self.complete_errors.pop(0)

    async def abort_multipart_upload(self, **kwargs):
        self.calls.append("abort")

    async def head_object(self, **kwargs):
        self.calls.append("head")
        if self.head_error:
            raise self.head_error
        return {}

    async def put_object(self, *, Key, Body, **kwargs):
        self.put_attempts[Key] = self.put_attempts.get(Key, 0) + 1
        if errors := self.put_errors.get(Key):
            raise errors.pop(0)
        self.put_bodies[Key] = Body

    async def get_object_stream(self, **kwargs):
        client = self

        class Body:
            def __init__(self):
                self._chunks = iter(client.download_chunks)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._chunks)
                except StopIteration:
                    raise StopAsyncIteration from None

            async def close(self):
                client.calls.append("close")

        return Body()


def make_agent(client: FakeClient, **performance) -> S3BackupAgent:
    entry = SimpleNamespace(
        data={
            "access_key_id": "key",
            "secret_access_key": "secret",
            "bucket": "bucket",
            "endpoint_url": "https://example.invalid",
            "upload_performance": performance,
        },
        title="bucket",
        entry_id="entry",
    )
    agent = S3BackupAgent(None, entry)

    @asynccontextmanager
    async def fake_create_client():
        yield client

    agent._create_client = fake_create_client
    return agent


def open_stream_factory(total: int, chunk_size: int = 64 * 1024):
    chunk = b"x" * chunk_size

    async def open_stream():
        async def gen():
            remaining = total
            while remaining > 0:
                piece = chunk if remaining >= chunk_size else chunk[:remaining]
                remaining -= len(piece)
                yield piece

        return gen()

    return open_stream


def upload(agent: S3BackupAgent, size: int):
    backup = AgentBackup(backup_id="b1", size=size)
    asyncio.run(
        agent.async_upload_backup(open_stream=open_stream_factory(size), backup=backup)
    )


def test_retries_throttling_then_succeeds(no_sleep):
    calls = []

    async def call(attempt):
        calls.append(attempt)
        if attempt < 2:
            raise client_error(503)
        return "ok"

    assert asyncio.run(with_retries("test", call)) == "ok"
    assert calls == [0, 1, 2]
    assert len(no_sleep) == 2


def test_retry_honors_retry_after(no_sleep):
    async def call(attempt):
        if attempt == 0:
            raise client_error(429, {"retry-after": "7"})
        return "ok"

    asyncio.run(with_retries("test", call))
    assert no_sleep == [7.0]


def test_retries_connection_errors_until_exhausted(no_sleep):
    async def call(attempt):
        raise S3ConnectionError("reset")

    with pytest.raises(S3ConnectionError):
        asyncio.run(with_retries("test", call))
    assert len(no_sleep) == backup_module.RETRY_ATTEMPTS - 1


def test_does_not_retry_permanent_client_errors(no_sleep):
    calls = []

    async def call(attempt):
        calls.append(attempt)
        raise client_error(403)

    with pytest.raises(ClientError):
        asyncio.run(with_retries("test", call))
    assert calls == [0]
    assert no_sleep == []


def test_rest_client_preserves_retry_response_metadata():
    class Response:
        status_code = 503
        headers = {"Retry-After": "5"}
        reason = "Service Unavailable"

        def __init__(self) -> None:
            self.closed = False

        def close(self):
            self.closed = True

    class Session:
        def __init__(self, response) -> None:
            self.response = response
            self.kwargs = {}

        def request(self, *args, **kwargs):
            self.kwargs = kwargs
            return self.response

    response = Response()
    client = S3RestClient(
        endpoint_url="https://s3.example.test",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
    )
    original_session = client._session
    session = Session(response)
    client._session = session

    try:
        with pytest.raises(ClientError) as err:
            client._request("GET", bucket="bucket")
    finally:
        original_session.close()

    assert err.value.status_code == 503
    assert err.value.headers == {"Retry-After": "5"}
    assert session.kwargs["timeout"] == (30, 300)
    assert response.closed


def test_rest_client_maps_timeout_to_connection_error():
    class Session:
        def request(self, *args, **kwargs):
            raise RequestsTimeout("timed out")

    client = S3RestClient(
        endpoint_url="https://s3.example.test",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
    )
    original_session = client._session
    client._session = Session()

    try:
        with pytest.raises(S3ConnectionError):
            client._request("GET", bucket="bucket")
    finally:
        original_session.close()


def test_retries_simple_and_metadata_uploads():
    client = FakeClient()
    client.put_errors = {
        "b1.tar": [client_error(503)],
        "b1.metadata.json": [client_error(503)],
    }
    agent = make_agent(client, part_size_mib=5)

    upload(agent, 1024)

    assert client.put_attempts == {"b1.tar": 2, "b1.metadata.json": 2}


def test_multipart_parts_are_equal_sized_bytearrays():
    client = FakeClient()
    agent = make_agent(client, part_size_mib=5, max_concurrency=2)
    upload(agent, 12 * MIB + 123)

    assert client.parts == {1: 5 * MIB, 2: 5 * MIB, 3: 2 * MIB + 123}
    assert client.part_types == {bytearray}
    assert client.calls == ["create", "complete"]
    assert "b1.metadata.json" in client.put_bodies


def test_simple_upload_keeps_bytearray_buffer():
    client = FakeClient()
    agent = make_agent(client, part_size_mib=5)
    upload(agent, 1024)

    assert isinstance(client.put_bodies["b1.tar"], bytearray)


def test_multipart_peak_memory_stays_near_two_parts():
    client = FakeClient()
    agent = make_agent(client, part_size_mib=5, max_concurrency=1)
    part = 5 * MIB

    tracemalloc.start()
    try:
        upload(agent, 10 * part)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert len(client.parts) == 10
    assert peak < 2.5 * part


def test_part_is_retried_after_server_error():
    client = FakeClient()
    client.upload_part_errors = [client_error(503)]
    agent = make_agent(client, part_size_mib=5)
    upload(agent, 11 * MIB)

    assert sorted(client.parts) == [1, 2, 3]
    assert client.calls == ["create", "complete"]


def test_multipart_creation_is_not_retried():
    client = FakeClient()
    client.create_errors = [client_error(503)]
    agent = make_agent(client, part_size_mib=5)

    with pytest.raises(BackupAgentError):
        upload(agent, 11 * MIB)

    assert client.calls == ["create"]


def test_lost_complete_response_is_confirmed_with_head():
    client = FakeClient()
    client.complete_errors = [client_error(503), client_error(404)]
    agent = make_agent(client, part_size_mib=5)
    upload(agent, 11 * MIB)

    assert client.calls == ["create", "complete", "complete", "head"]


def test_complete_404_without_object_aborts():
    client = FakeClient()
    client.complete_errors = [client_error(503), client_error(404)]
    client.head_error = client_error(404)
    agent = make_agent(client, part_size_mib=5)

    with pytest.raises(BackupAgentError):
        upload(agent, 11 * MIB)

    assert client.calls[-1] == "abort"


def test_download_streams_chunks_and_closes(monkeypatch):
    client = FakeClient()
    client.download_chunks = [b"a" * 10, b"b" * 10]
    agent = make_agent(client)
    backup = AgentBackup(backup_id="b1", size=20)

    async def find(_backup_id):
        return backup

    monkeypatch.setattr(agent, "_find_backup_by_id", find)

    async def read_all():
        stream = await agent.async_download_backup("b1")
        return b"".join([chunk async for chunk in stream])

    assert asyncio.run(read_all()) == b"a" * 10 + b"b" * 10
    assert client.calls == ["close"]


def test_streaming_body_reads_response_in_chunks_and_closes():
    class Response:
        def __init__(self) -> None:
            self.closed = False
            self.chunk_size = None

        def iter_content(self, chunk_size):
            self.chunk_size = chunk_size
            return iter([b"first", b"second"])

        def close(self):
            self.closed = True

    response = Response()
    body = _StreamingBody(response)

    async def read_all():
        chunks = [chunk async for chunk in body]
        await body.close()
        return chunks

    assert asyncio.run(read_all()) == [b"first", b"second"]
    assert response.chunk_size == 2**20
    assert response.closed

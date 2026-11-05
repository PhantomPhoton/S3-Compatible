"""Unit tests for streaming backup uploads and downloads."""

import asyncio
import tracemalloc
from contextlib import asynccontextmanager
from types import SimpleNamespace

from custom_components.s3_compatible.backup import S3BackupAgent
from custom_components.s3_compatible.s3rest import _StreamingBody
from homeassistant.components.backup import AgentBackup

MIB = 2**20


class FakeClient:
    def __init__(self) -> None:
        self.parts: dict[int, int] = {}
        self.part_types: set[type] = set()
        self.calls: list[str] = []
        self.put_bodies: dict[str, object] = {}
        self.download_chunks: list[bytes] = []

    async def create_multipart_upload(self, **kwargs):
        self.calls.append("create")
        return {"UploadId": "upload-1"}

    async def upload_part(self, *, PartNumber, Body, **kwargs):
        self.parts[PartNumber] = len(Body)
        self.part_types.add(type(Body))
        return {"ETag": f"etag-{PartNumber}"}

    async def complete_multipart_upload(self, **kwargs):
        self.calls.append("complete")

    async def abort_multipart_upload(self, **kwargs):
        self.calls.append("abort")

    async def put_object(self, *, Key, Body, **kwargs):
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

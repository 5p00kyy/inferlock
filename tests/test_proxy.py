import asyncio
import fcntl
import importlib
import json

import httpx
import pytest
from httpx import ASGITransport, AsyncByteStream, MockTransport, Response
from starlette.requests import Request
from starlette.responses import StreamingResponse

proxy_module = importlib.import_module("proxies.llama-safe-proxy")


class SlowStream(AsyncByteStream):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __aiter__(self):
        self.started.set()
        yield b"data: first\n\n"
        await self.release.wait()
        yield b"data: second\n\n"


def assert_lock_available(path):
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def assert_lock_held(path):
    f = open(path, "w")
    try:
        with pytest.raises(BlockingIOError):
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        f.close()


@pytest.fixture(autouse=True)
def proxy_env(monkeypatch, tmp_path):
    lock_path = tmp_path / "gpu.lock"
    lock_path.write_text("")
    monkeypatch.setattr(proxy_module, "LOCK_PATH", str(lock_path))
    monkeypatch.setattr(proxy_module, "BACKEND", "http://backend")
    monkeypatch.setattr(proxy_module, "prepare_llama", lambda: None)
    yield lock_path


@pytest.mark.asyncio
async def test_non_streaming_gpu_request_releases_lock(proxy_env):
    def handler(request):
        assert request.url == "http://backend/v1/chat/completions"
        return Response(200, json={"ok": True})

    await proxy_module.client.aclose()
    proxy_module.client = httpx.AsyncClient(transport=MockTransport(handler), timeout=None)

    async with httpx.AsyncClient(transport=ASGITransport(app=proxy_module.app), base_url="http://proxy") as client:
        response = await client.post("/v1/chat/completions", json={"model": "demo"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert_lock_available(proxy_env)


@pytest.mark.asyncio
async def test_streaming_gpu_request_holds_lock_until_stream_closes(proxy_env):
    stream = SlowStream()
    body = json.dumps({"model": "demo", "stream": True}).encode()

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return Response(200, stream=stream, headers={"content-type": "text/event-stream"})

    await proxy_module.client.aclose()
    proxy_module.client = httpx.AsyncClient(transport=MockTransport(handler), timeout=None)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
        "server": ("proxy", 80),
        "scheme": "http",
        "client": ("testclient", 50000),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    response = await proxy_module.proxy(Request(scope, receive), "v1/chat/completions")
    assert isinstance(response, StreamingResponse)

    iterator = response.body_iterator.__aiter__()
    first = await anext(iterator)
    await asyncio.wait_for(stream.started.wait(), timeout=1)
    assert b"data: first" in first
    assert_lock_held(proxy_env)

    stream.release.set()
    rest = b"".join([chunk async for chunk in iterator])

    assert b"data: second" in rest
    assert_lock_available(proxy_env)


def test_safe_reads_do_not_need_gpu():
    assert proxy_module.needs_gpu("GET", "v1/models") is False
    assert proxy_module.needs_gpu("GET", "api/v1/models") is False
    assert proxy_module.needs_gpu("GET", "health") is False
    assert proxy_module.needs_gpu("POST", "v1/chat/completions") is True
    assert proxy_module.body_requests_stream(b'{"stream": true}') is True



@pytest.mark.asyncio
async def test_gpu_request_lock_timeout_returns_503(proxy_env, monkeypatch):
    holder = open(proxy_env, "w")
    fcntl.flock(holder, fcntl.LOCK_EX)
    monkeypatch.setattr(proxy_module, "LOCK_TIMEOUT", 0.05)
    monkeypatch.setattr(proxy_module, "LOCK_RETRY_SECONDS", 0.01)

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=proxy_module.app), base_url="http://proxy") as client:
            response = await client.post("/v1/chat/completions", json={"model": "demo"})
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()

    assert response.status_code == 503
    assert "timed out waiting for GPU lock" in response.text
    assert_lock_available(proxy_env)

#!/usr/bin/env python3
"""GPU-safe proxy for a public llama.cpp endpoint.

The real llama.cpp router should listen only on loopback. This proxy owns the
public endpoint, stops the competing engine before GPU-using llama requests, and
holds a shared file lock until the request or stream completes.
"""
import asyncio
import fcntl
import json
import os
import subprocess
import time

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

BACKEND = os.environ.get("LLAMA_PROXY_BACKEND", "http://127.0.0.1:8082")
LOCK_PATH = os.environ.get("INFERENCE_GPU_LOCK", "/run/inference-gpu.lock")
COORDINATOR = os.environ.get("INFERENCE_COORDINATOR", "/opt/inferlock/scripts/inference-coordinator.sh")
PREPARE_TIMEOUT = float(os.environ.get("PREPARE_LLAMA_TIMEOUT", "180"))
LOCK_TIMEOUT = float(os.environ.get("INFERENCE_GPU_LOCK_TIMEOUT", "300"))
LOCK_RETRY_SECONDS = float(os.environ.get("INFERENCE_GPU_LOCK_RETRY_SECONDS", "0.1"))

app = FastAPI(title="llama.cpp GPU-safe proxy")
client = httpx.AsyncClient(timeout=None)

SAFE_READS = {
    ("GET", "health"),
    ("GET", "props"),
    ("GET", "models"),
    ("GET", "v1/models"),
    ("GET", "api/v1/models"),
}


def needs_gpu(method: str, path: str) -> bool:
    norm = path.strip("/")
    if (method.upper(), norm) in SAFE_READS:
        return False
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    if norm in {"slots", "metrics"}:
        return True
    return False


def acquire_gpu_lock():
    f = open(LOCK_PATH, "w")
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except BlockingIOError:
            if time.monotonic() >= deadline:
                f.close()
                raise TimeoutError(f"timed out waiting for GPU lock {LOCK_PATH}")
            time.sleep(min(LOCK_RETRY_SECONDS, max(0.0, deadline - time.monotonic())))


def release_gpu_lock(f):
    if f is not None:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        finally:
            f.close()


def prepare_llama():
    subprocess.run([COORDINATOR, "prepare-llama-unlocked"], check=True, timeout=PREPARE_TIMEOUT)


def body_requests_stream(body: bytes) -> bool:
    if not body:
        return False
    try:
        return bool(json.loads(body.decode() or "{}").get("stream"))
    except Exception:
        return b'"stream"' in body


@app.get("/_proxy/health")
async def proxy_health():
    return {"ok": True, "backend": BACKEND, "lock": LOCK_PATH}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(request: Request, path: str):
    method = request.method.upper()
    target = f"{BACKEND}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    body = await request.body()
    lock_file = None

    if needs_gpu(method, path):
        try:
            lock_file = await asyncio.to_thread(acquire_gpu_lock)
            await asyncio.to_thread(prepare_llama)
        except Exception as e:
            release_gpu_lock(lock_file)
            return Response(content=f"GPU coordinator failed before llama request: {e}\n", status_code=503, media_type="text/plain")

    if body_requests_stream(body):
        try:
            upstream_req = client.build_request(method, target, content=body, headers=headers)
            upstream = await client.send(upstream_req, stream=True)
        except Exception as e:
            release_gpu_lock(lock_file)
            return Response(content=f"Upstream llama stream failed: {e}\n", status_code=502, media_type="text/plain")

        async def gen():
            nonlocal lock_file, upstream
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                release_gpu_lock(lock_file)
                lock_file = None

        return StreamingResponse(gen(), status_code=upstream.status_code, media_type=upstream.headers.get("content-type") or "text/event-stream")

    try:
        r = await client.request(method, target, content=body, headers=headers)
        return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))
    finally:
        release_gpu_lock(lock_file)

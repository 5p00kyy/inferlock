"""Integration sketch for a vLLM switch router.

Use the same lock around model ensure/start and the proxied upstream request.
For streaming, release the lock only after the upstream stream closes.
"""
import asyncio
import fcntl
import os
import subprocess
import time

GPU_LOCK_PATH = os.environ.get("INFERENCE_GPU_LOCK", "/run/inference-gpu.lock")
GPU_LOCK_TIMEOUT = float(os.environ.get("INFERENCE_GPU_LOCK_TIMEOUT", "300"))
GPU_LOCK_RETRY_SECONDS = float(os.environ.get("INFERENCE_GPU_LOCK_RETRY_SECONDS", "0.1"))
COORDINATOR = os.environ.get("INFERENCE_COORDINATOR", "/opt/inferlock/scripts/inference-coordinator.sh")


def acquire_gpu_lock():
    f = open(GPU_LOCK_PATH, "w")
    deadline = time.monotonic() + GPU_LOCK_TIMEOUT
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except BlockingIOError:
            if time.monotonic() >= deadline:
                f.close()
                raise TimeoutError(f"timed out waiting for GPU lock {GPU_LOCK_PATH}")
            time.sleep(min(GPU_LOCK_RETRY_SECONDS, max(0.0, deadline - time.monotonic())))


def release_gpu_lock(f) -> None:
    if f is not None:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        finally:
            f.close()


def prepare_vllm_locked() -> None:
    subprocess.run([COORDINATOR, "prepare-vllm-unlocked"], check=True, timeout=240)


async def before_vllm_request():
    gpu_lock = await asyncio.to_thread(acquire_gpu_lock)
    try:
        await asyncio.to_thread(prepare_vllm_locked)
        # ensure/start requested vLLM model here. Pass INFERENCE_GPU_LOCK_HELD=1
        # to nested start scripts that also call the coordinator.
        return gpu_lock
    except Exception:
        release_gpu_lock(gpu_lock)
        raise


async def finish_vllm_request(gpu_lock):
    release_gpu_lock(gpu_lock)

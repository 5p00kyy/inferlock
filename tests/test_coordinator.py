import fcntl
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inference-coordinator.sh"
FAKE_UNLOAD = ROOT / "tests" / "fake_unload.py"


class FakeLlamaRouter(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        status = "unloaded" if self.server.unloaded else "loaded"
        self._json({"data": [{"id": "demo", "status": {"value": status}}]})

    def do_POST(self):
        if self.path != "/models/unload":
            self.send_response(404)
            self.end_headers()
            return
        self.server.unloaded = True
        self.server.unload_calls += 1
        body = b'{"error":{"message":"model is not found"}}'
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def start_fake_llama_router():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLlamaRouter)
    server.unloaded = False
    server.unload_calls = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def run_prepare_vllm(env, name):
    proc_env = dict(env, FAKE_ENGINE_NAME=name)
    return subprocess.Popen(
        [str(SCRIPT), "prepare-vllm"],
        cwd=ROOT,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def parse_events(log_path):
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        action, name, stamp = line.split()
        events.append((action, name, float(stamp)))
    return events


def test_prepare_vllm_serializes_unload_command_with_shared_lock(tmp_path):
    log_path = tmp_path / "events.log"
    lock_path = tmp_path / "gpu.lock"
    env = dict(
        os.environ,
        INFERENCE_GPU_LOCK=str(lock_path),
        LLAMA_UNLOAD_CMD=f"{sys.executable} {FAKE_UNLOAD}",
        FAKE_ENGINE_LOG=str(log_path),
        FAKE_ENGINE_DELAY="0.2",
    )

    first = run_prepare_vllm(env, "first")
    time.sleep(0.05)
    second = run_prepare_vllm(env, "second")

    first_out, first_err = first.communicate(timeout=5)
    second_out, second_err = second.communicate(timeout=5)

    assert first.returncode == 0, first_out + first_err
    assert second.returncode == 0, second_out + second_err

    events = parse_events(log_path)
    by_name = {name: {} for _, name, _ in events}
    for action, name, stamp in events:
        by_name[name][action] = stamp

    assert set(by_name) == {"first", "second"}
    first_window = by_name["first"]
    second_window = by_name["second"]

    # One fake unload must fully finish before the other starts. If the shared
    # flock is removed or bypassed, these windows overlap and this assertion
    # fails reliably because each command sleeps for FAKE_ENGINE_DELAY.
    assert (
        first_window["end"] <= second_window["start"]
        or second_window["end"] <= first_window["start"]
    )


def test_api_key_file_is_read_without_shelling_secret(tmp_path):
    key_file = tmp_path / "api-key"
    key_file.write_text("secret-from-file", encoding="utf-8")
    env = dict(
        os.environ,
        INFERENCE_GPU_LOCK=str(tmp_path / "gpu.lock"),
        LLAMA_API_KEY_FILE=str(key_file),
        LLAMA_UNLOAD_CMD="test \"$LLAMA_API_KEY\" = secret-from-file",
    )

    result = subprocess.run(
        [str(SCRIPT), "prepare-vllm"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
    )

    assert result.returncode == 0, result.stdout + result.stderr



def test_llama_unload_treats_400_model_not_found_as_already_unloaded(tmp_path):
    server, thread = start_fake_llama_router()
    try:
        env = dict(
            os.environ,
            INFERENCE_GPU_LOCK=str(tmp_path / "gpu.lock"),
            LLAMA_BACKEND=f"http://127.0.0.1:{server.server_port}",
            LLAMA_UNLOAD_TIMEOUT="2",
        )

        result = subprocess.run(
            [str(SCRIPT), "prepare-vllm"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stdout + result.stderr
    assert server.unload_calls == 1


def test_prepare_vllm_lock_timeout_fails_instead_of_blocking_forever(tmp_path):
    lock_path = tmp_path / "gpu.lock"
    holder = open(lock_path, "w")
    try:
        fcntl.flock(holder, fcntl.LOCK_EX)
        env = dict(
            os.environ,
            INFERENCE_GPU_LOCK=str(lock_path),
            INFERENCE_GPU_LOCK_TIMEOUT="0.2",
            LLAMA_UNLOAD_CMD="true",
        )

        start = time.monotonic()
        result = subprocess.run(
            [str(SCRIPT), "prepare-vllm"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=3,
        )
        elapsed = time.monotonic() - start
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()

    assert result.returncode != 0
    assert elapsed < 2


def test_prepare_llama_reports_vllm_stop_script_failure_immediately(tmp_path):
    stop_script = tmp_path / "stop-vllm.sh"
    stop_script.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    stop_script.chmod(0o755)
    env = dict(
        os.environ,
        INFERENCE_GPU_LOCK=str(tmp_path / "gpu.lock"),
        VLLM_STOP=str(stop_script),
        VLLM_STOP_TIMEOUT="5",
    )

    start = time.monotonic()
    result = subprocess.run(
        [str(SCRIPT), "prepare-llama"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=3,
    )
    elapsed = time.monotonic() - start

    assert result.returncode == 7
    assert elapsed < 2

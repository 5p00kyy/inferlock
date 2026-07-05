import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inference-coordinator.sh"
FAKE_UNLOAD = ROOT / "tests" / "fake_unload.py"


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

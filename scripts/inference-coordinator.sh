#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
LLAMA_BACKEND="${LLAMA_BACKEND:-http://127.0.0.1:8082}"
VLLM_BACKEND="${VLLM_BACKEND:-http://127.0.0.1:8090}"
VLLM_STOP="${VLLM_STOP:-/opt/vllm/stop.sh}"
LLAMA_UNLOAD_TIMEOUT="${LLAMA_UNLOAD_TIMEOUT:-180}"
VLLM_STOP_TIMEOUT="${VLLM_STOP_TIMEOUT:-120}"

if [[ -n "${LLAMA_API_KEY_FILE:-}" && -r "${LLAMA_API_KEY_FILE}" ]]; then
  LLAMA_API_KEY="$(<"${LLAMA_API_KEY_FILE}")"
else
  LLAMA_API_KEY="${LLAMA_API_KEY:-}"
fi
export LLAMA_BACKEND VLLM_BACKEND VLLM_STOP LLAMA_API_KEY LLAMA_UNLOAD_TIMEOUT VLLM_STOP_TIMEOUT

unload_llama() {
  python3 - <<'PY'
import json, os, time, urllib.request, urllib.error
base = os.environ.get('LLAMA_BACKEND', 'http://127.0.0.1:8082')
key = os.environ.get('LLAMA_API_KEY', '')
timeout = float(os.environ.get('LLAMA_UNLOAD_TIMEOUT', '180'))
headers = {'Authorization': f'Bearer {key}'} if key else {}

def req(path, data=None, timeout=10):
    body = None
    h = dict(headers)
    if data is not None:
        body = json.dumps(data).encode()
        h['Content-Type'] = 'application/json'
    return urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=h), timeout=timeout)

def loaded_models():
    try:
        with req('/v1/models', timeout=10) as r:
            data = json.load(r).get('data', [])
    except Exception:
        return []
    return [m.get('id') for m in data if (m.get('status') or {}).get('value') not in (None, 'unloaded')]

for model in [m for m in loaded_models() if m]:
    try:
        with req('/models/unload', {'model': model}, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        if e.code not in (404, 409):
            raise

deadline = time.time() + timeout
while time.time() < deadline:
    if not loaded_models():
        print('llama_unloaded')
        break
    time.sleep(2)
else:
    raise SystemExit('timed out waiting for llama models to unload')
PY
}

stop_vllm() {
  if [[ -x "$VLLM_STOP" ]]; then
    "$VLLM_STOP" >/dev/null 2>&1 || true
  fi
  python3 - <<'PY'
import os, time, urllib.request
base = os.environ.get('VLLM_BACKEND', 'http://127.0.0.1:8090')
timeout = float(os.environ.get('VLLM_STOP_TIMEOUT', '120'))
deadline = time.time() + timeout
while time.time() < deadline:
    try:
        urllib.request.urlopen(base + '/health', timeout=2).read()
    except Exception:
        print('vllm_stopped')
        break
    time.sleep(1)
else:
    raise SystemExit('timed out waiting for vLLM backend to stop')
PY
}

case "$ACTION" in
  prepare-vllm-unlocked)
    unload_llama
    ;;
  prepare-llama-unlocked)
    stop_vllm
    ;;
  status)
    curl -sS "$LLAMA_BACKEND/health" || true; echo
    curl -sS "$VLLM_BACKEND/health" || true; echo
    nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits || true
    ;;
  *)
    echo "usage: $0 {prepare-vllm-unlocked|prepare-llama-unlocked|status}" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

# Example loopback-only llama.cpp router start script for llama-server-loopback.service.
# Copy this to /opt/llama/llama-server.sh and adjust paths for your host.
#
# Important for router mode: child model idle sleep is controlled by the model
# preset, not just the parent router process. Add a global preset like:
#
#   [*]
#   sleep-idle-seconds = 1800
#
# or add sleep-idle-seconds to each model section in LLAMA_MODELS_PRESET.

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-/usr/local/bin/llama-server}"
LLAMA_BIND_HOST="${LLAMA_BIND_HOST:-127.0.0.1}"
LLAMA_BIND_PORT="${LLAMA_BIND_PORT:-8082}"
LLAMA_MODELS_DIR="${LLAMA_MODELS_DIR:-/opt/llama/models}"
LLAMA_MODELS_PRESET="${LLAMA_MODELS_PRESET:-/opt/llama/presets.ini}"
LLAMA_MODELS_MAX="${LLAMA_MODELS_MAX:-1}"
LLAMA_IDLE_UNLOAD_SECONDS="${LLAMA_IDLE_UNLOAD_SECONDS:-1800}"
LLAMA_API_KEY_FILE="${LLAMA_API_KEY_FILE:-/run/secrets/llama-api-key}"

args=(
  --host "$LLAMA_BIND_HOST"
  --port "$LLAMA_BIND_PORT"
  --models-dir "$LLAMA_MODELS_DIR"
  --models-preset "$LLAMA_MODELS_PRESET"
  --models-max "$LLAMA_MODELS_MAX"
  --sleep-idle-seconds "$LLAMA_IDLE_UNLOAD_SECONDS"
  --no-warmup
)

if [[ -r "$LLAMA_API_KEY_FILE" ]]; then
  args+=(--api-key "$(<"$LLAMA_API_KEY_FILE")")
fi

exec "$LLAMA_SERVER_BIN" "${args[@]}" "$@"

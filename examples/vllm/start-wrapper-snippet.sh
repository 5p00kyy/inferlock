#!/usr/bin/env bash
set -euo pipefail

# Run this before starting a vLLM backend. If the caller already holds the shared
# lock, set INFERENCE_GPU_LOCK_HELD=1 to avoid deadlock.
if [[ "${INFERENCE_GPU_LOCK_HELD:-0}" != "1" ]]; then
  flock -x "${INFERENCE_GPU_LOCK:-/run/inference-gpu.lock}" \
    "${INFERENCE_COORDINATOR:-/opt/llm-gpu-coordinator/scripts/inference-coordinator.sh}" prepare-vllm-unlocked
else
  "${INFERENCE_COORDINATOR:-/opt/llm-gpu-coordinator/scripts/inference-coordinator.sh}" prepare-vllm-unlocked
fi

# Start vLLM here, for example:
# exec bash /opt/vllm/run-profile.sh "${1:-default}"

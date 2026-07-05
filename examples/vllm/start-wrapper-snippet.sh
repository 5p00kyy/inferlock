#!/usr/bin/env bash
set -euo pipefail

# Run this before starting a vLLM backend. The coordinator takes the shared lock
# itself. If the caller already holds the lock, set INFERENCE_GPU_LOCK_HELD=1 to
# avoid deadlock.
"${INFERENCE_COORDINATOR:-/opt/llm-gpu-coordinator/scripts/inference-coordinator.sh}" prepare-vllm

# Start vLLM here, for example:
# exec bash /opt/vllm/run-profile.sh "${1:-default}"

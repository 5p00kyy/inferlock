# Inferlock

Exclusive GPU leases for local LLM inference engines.

Small coordination layer for machines that run multiple local LLM engines on the same GPU pool, for example a llama.cpp router and a vLLM OpenAI-compatible server.

The goal is simple: requests to either public endpoint should not accidentally overlap GPU-heavy engines. If llama.cpp is about to serve a request, vLLM is stopped first. If vLLM is about to serve a request, loaded llama.cpp router models are unloaded first. A shared file lock serializes the handoff and stays held for the full request, including streaming responses.

This started as homelab glue. The public-worthy shape is a narrower "GPU lease" helper for local inference engines, not another full LLM gateway. See `docs/public-roadmap.md` and `docs/landscape.md`.

## When to use this

Use this when several cooperating local inference engines can all claim the same GPU and you need a conservative handoff guard before any one of them touches CUDA.

Good fit:

- one workstation or homelab box with llama.cpp and vLLM sharing the same GPU pool
- a custom router that needs to stop/unload competing engines before proxying a request
- systemd or shell-managed inference services that need one shared lock contract
- streaming requests where the lock must stay held until the stream closes

Not the right tool:

- use llama-swap if you mainly need model/process hot-swapping and it already supervises your engines
- use LiteLLM or Portkey if you need provider routing, keys, budgets, retries, or API accounting
- use LoxyRouter if you have multiple already-running backends and want warmth-aware routing
- use vLLM Production Stack if you are building a Kubernetes/distributed vLLM deployment

## Components

- `scripts/inference-coordinator.sh`: shared stop/unload coordinator. Use `prepare-llama` or `prepare-vllm` for lock-taking calls; use the `*-unlocked` variants only when the caller already holds `INFERENCE_GPU_LOCK`.
- `proxies/llama-safe-proxy.py`: FastAPI/httpx proxy that fronts a private llama.cpp router endpoint.
- `examples/systemd/`: example systemd units.
- `examples/vllm/`: integration snippets for a vLLM switch router/start script.
- `tests/`: regression tests for the proxy lock behavior, especially streaming lock lifetime.

## Endpoint pattern

Example layout:

- Public llama endpoint: `0.0.0.0:8080`, served by `llama-safe-proxy.py`.
- Real llama.cpp router: `127.0.0.1:8082`, not exposed directly.
- Public vLLM switch router: `0.0.0.0:8091`.
- Real vLLM backend: `127.0.0.1:8090`, started/stopped by the switch router.
- Shared lock: `/run/inference-gpu.lock`.

Direct access to the private backend ports bypasses coordination. Keep those loopback-only.

## Install

```bash
git clone https://github.com/5p00kyy/inferlock.git
cd inferlock
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

For a system install, copy or clone the repo to `/opt/inferlock`, then adapt the example systemd units in `examples/systemd/`. Keep real inference backends loopback-only and expose only coordinated proxy/router ports.

## Required environment

For the coordinator:

```bash
export LLAMA_BACKEND=http://127.0.0.1:8082
export VLLM_BACKEND=http://127.0.0.1:8090
export LLAMA_API_KEY_FILE=/run/secrets/llama-api-key
export VLLM_STOP=/opt/vllm/stop.sh
export INFERENCE_GPU_LOCK=/run/inference-gpu.lock
```

`LLAMA_API_KEY` is also accepted, but a file is preferred. Do not hard-code secrets in scripts or units.

For generic/fake adapters, `LLAMA_UNLOAD_CMD` can replace the built-in llama.cpp unload call:

```bash
export LLAMA_UNLOAD_CMD='systemctl stop some-llama-service'
```

Configured shell commands are trusted operator configuration. Do not pass untrusted user input into them.

## Coordinator commands

```bash
# Safe public entry points: take the shared lock, then perform the handoff.
scripts/inference-coordinator.sh prepare-llama
scripts/inference-coordinator.sh prepare-vllm

# Internal entry points: only call when the caller already owns INFERENCE_GPU_LOCK.
scripts/inference-coordinator.sh prepare-llama-unlocked
scripts/inference-coordinator.sh prepare-vllm-unlocked

scripts/inference-coordinator.sh status
```

If a caller already holds the lock and needs to call the coordinator recursively, set `INFERENCE_GPU_LOCK_HELD=1` before calling `prepare-llama` or `prepare-vllm`.

## Streaming safety

Streaming responses are the easy place to get this wrong. The proxy/router must not release the GPU lock when it returns a `StreamingResponse`; it must release the lock only after the upstream stream is closed or cancelled.

Both included examples follow that rule.

## Testing

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
bash -n scripts/inference-coordinator.sh examples/vllm/start-wrapper-snippet.sh
```

CI also runs ShellCheck and a small secret-pattern smoke check.

## Status

Prototype, extracted from a working homelab setup. Treat the included systemd files as examples, not drop-in production config.

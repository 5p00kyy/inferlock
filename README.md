# llm-gpu-coordinator

Small coordination layer for machines that run multiple local LLM engines on the same GPU pool, for example a llama.cpp router and a vLLM OpenAI-compatible server.

The goal is simple: requests to either public endpoint should not accidentally overlap GPU-heavy engines. If llama.cpp is about to serve a request, vLLM is stopped first. If vLLM is about to serve a request, loaded llama.cpp router models are unloaded first. A shared file lock serializes the handoff and stays held for the full request, including streaming responses.

This started as homelab glue, but the pattern should be reusable.

## Components

- `scripts/inference-coordinator.sh`: shared stop/unload coordinator.
- `proxies/llama-safe-proxy.py`: FastAPI/httpx proxy that fronts a private llama.cpp router endpoint.
- `examples/systemd/`: example systemd units.
- `examples/vllm/`: integration snippets for a vLLM switch router/start script.

## Endpoint pattern

Example layout:

- Public llama endpoint: `0.0.0.0:8080`, served by `llama-safe-proxy.py`.
- Real llama.cpp router: `127.0.0.1:8082`, not exposed directly.
- Public vLLM switch router: `0.0.0.0:8091`.
- Real vLLM backend: `127.0.0.1:8090`, started/stopped by the switch router.
- Shared lock: `/run/inference-gpu.lock`.

Direct access to the private backend ports bypasses coordination. Keep those loopback-only.

## Required environment

For the coordinator:

```bash
export LLAMA_BACKEND=http://127.0.0.1:8082
export VLLM_BACKEND=http://127.0.0.1:8090
export LLAMA_API_KEY_FILE=/run/secrets/llama-api-key
export VLLM_STOP=/opt/vllm/stop.sh
```

`LLAMA_API_KEY` is also accepted, but a file is preferred. Do not hard-code secrets in scripts or units.

## Streaming safety

Streaming responses are the easy place to get this wrong. The proxy/router must not release the GPU lock when it returns a `StreamingResponse`; it must release the lock only after the upstream stream is closed or cancelled.

Both included examples follow that rule.

## Status

Prototype, extracted from a working homelab setup. Treat the included systemd files as examples, not drop-in production config.

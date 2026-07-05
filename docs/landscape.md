# Landscape research

This project should be positioned as a GPU lease and handoff layer, not as another general LLM gateway. The existing public projects mostly cluster into four categories.

## 1. Model/process hot-swap

### llama-swap

Link: https://github.com/mostlygeek/llama-swap

The closest established project. It fronts local OpenAI/Anthropic-compatible engines, starts the requested model process, stops the wrong one, supports TTL idle unload, Docker/Podman process control, status/log endpoints, and a newer swap matrix for concurrent model groups.

Overlap: high for model lifecycle and one-machine swapping.

Gap for this repo: llama-swap is the thing that supervises model processes. It is not specifically a small lease primitive that other tools can call before touching CUDA, and it does not make exclusive GPU ownership the central public abstraction.

### ClaraCore

Link: https://github.com/claraverse-space/ClaraCore

Extends llama-swap with automatic GGUF discovery, hardware detection, llama.cpp binary management, and generated production-ish configs.

Overlap: medium. It improves llama-swap setup for llama.cpp users.

Gap for this repo: focused on easier llama.cpp deployment, not cross-engine lease safety.

### llama-swap vLLM boilerplates and containers

Examples:

- https://github.com/meganoob1337/llama-swap-vllm-boilerplate
- https://github.com/bjodah/llm-multi-backend-container
- https://github.com/mARTin-B78/dgx-spark_lite-llm_llama-swap_vllm_llama-cpp_ollama

These validate demand for llama.cpp plus vLLM plus a unified OpenAI-compatible front door. The DGX Spark stack uses the common shape: client -> LiteLLM -> llama-swap -> vLLM/llama.cpp/Ollama.

Overlap: medium as deployment examples.

Gap for this repo: they are stack recipes around llama-swap, not a reusable coordination primitive.

## 2. Warmth-aware or VRAM-aware routing

### LoxyRouter

Link: https://github.com/mageshkrishna/loxy-router

A warmth-aware router for Ollama/vLLM backends. It routes to the backend where the requested model is already loaded, polls backend state, has a VRAM guard, hard concurrency caps, priority queues, conversation affinity, Prometheus metrics, and a clear comparison page.

Overlap: medium-high for local inference routing and VRAM safety.

Gap for this repo: it deliberately does not spawn or supervise backends. It assumes backends already exist and chooses between them. It does not solve single-GPU engine handoff between llama.cpp and vLLM, and it does not expose a generic exclusive lease wrapper for arbitrary engine start scripts.

### SmarterRouter

Link: https://github.com/peva3/SmarterRouter

An intelligent local LLM gateway with prompt-based model routing, model profiling, semantic cache, VRAM monitoring, auto-unload, and Ollama/llama.cpp/OpenAI-style backend support.

Overlap: high at the marketing level because it says VRAM-aware router.

Gap for this repo: it is a larger gateway and model-selection system. Its public docs frame VRAM management around backend support and automated routing, not a minimal lease/handoff contract that scripts, proxies, systemd units, or other gateways can share.

## 3. API gateways

### LiteLLM

Link: https://github.com/BerriAI/litellm

The dominant API gateway layer: provider normalization, OpenAI-compatible API, routing, keys, budgets, fallbacks, retries, logs, and local provider support.

Overlap: low. It can sit above local inference.

Gap for this repo: no local GPU ownership, no engine lifecycle, no exclusive CUDA handoff.

### Portkey Gateway

Link: https://github.com/Portkey-AI/gateway

Similar broad AI gateway category: provider routing, guardrails, caching, observability, API management.

Overlap: low.

Gap for this repo: not a local GPU coordinator.

## 4. vLLM production/distributed stacks

### vLLM Production Stack

Link: https://github.com/vllm-project/production-stack

Kubernetes and Helm reference stack for production vLLM deployments, with request routing, monitoring, KV cache aware work, autoscaling direction, and distributed serving concerns.

Overlap: low-medium for production inference routing.

Gap for this repo: vLLM-only and Kubernetes-oriented. It does not address a homelab/workstation style single host where different engines need an exclusive GPU lease before startup.

## Public opportunity

The useful niche is not:

- full model routing
- intelligent prompt/model selection
- multi-provider API gateway
- another llama-swap clone
- Kubernetes scheduling

The useful niche is:

> A tiny, composable GPU lease layer for local inference engines.

Core promise:

1. Acquire the lease before an engine touches CUDA.
2. Run configured handoff actions while holding the lease.
3. Keep the lease for the full request, including streaming responses.
4. Release on completion, failure, or cancellation.
5. Make it easy for shell scripts, Python routers, systemd services, and existing gateways to compose around the same lock.

## Practical public-readiness implications

The README should compare directly against llama-swap, LoxyRouter, SmarterRouter, LiteLLM, and vLLM Production Stack. The comparison should be honest: users who only need model hot-swap should probably use llama-swap. Users with multiple always-running backends should look at LoxyRouter. Users who need keys/provider routing should use LiteLLM. This project is for the awkward gap where several local engines can all claim the same GPU and the operator wants a conservative handoff guard.

The implementation should prioritize:

- a small config format
- generic engine adapters
- fake-engine CI tests
- cancellation/failure lock-release tests
- examples showing composition underneath LiteLLM or alongside llama-swap
- SECURITY.md explaining that this is coordination, not isolation

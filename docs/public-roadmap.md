# Public-readiness notes

This repository should not try to be a full OpenAI gateway. Existing projects already cover that layer well:

- llama-swap: model/process hot swapping and idle unload in front of OpenAI-compatible engines.
- ClaraCore and llama-swap boilerplates: easier deployment and stack recipes for llama.cpp/vLLM/Ollama.
- LiteLLM/Portkey: API normalization, keys, routing, retries, accounting.
- LoxyRouter/SmarterRouter-style projects: backend/model routing, VRAM guards, model choice, caching.
- vLLM Production Stack: Kubernetes/distributed vLLM serving.

The reusable gap here is narrower: an operational lease around shared GPU ownership. See `docs/landscape.md` for research notes.

## Proposed public positioning

Project name: **Inferlock**.

Subtitle: exclusive GPU leases for local inference engines.

Core promise:

> Before an inference engine touches CUDA, it acquires a shared GPU lease. The lease can stop or unload conflicting engines, remains held for the full request including streams, and is released on completion or cancellation.

## What belongs in scope

- File-lock based GPU leases that work from shell, Python, and systemd units.
- Conservative engine handoff between llama.cpp, vLLM, Ollama, TGI, and generic OpenAI-compatible engines.
- Stream-safe proxy examples that hold the lease until upstream close/cancel.
- Generic start/stop/health adapters for supervised services.
- Clear integration examples for use underneath LiteLLM, alongside llama-swap, or inside a custom router.
- Tests for failed handoff, stream cancellation, and stale process cleanup.

## What should stay out of scope, at least initially

- Prompt-based model selection.
- Cloud provider routing.
- Billing/accounting/virtual keys.
- Security isolation. This is coordination glue, not a sandbox.
- A full hosted dashboard.

## Minimum bar before making public

- No homelab paths in default docs, only examples.
- Config file or documented environment contract for every path/port/command.
- Tests proving locks are held across streaming responses.
- Tests proving locks are released after upstream failure/cancellation.
- Systemd examples that keep private backend ports loopback-only.
- README comparison explaining when to use llama-swap, LoxyRouter, SmarterRouter, LiteLLM, vLLM Production Stack, or this project.

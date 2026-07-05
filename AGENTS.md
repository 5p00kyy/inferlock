# AGENTS.md

This repo contains GPU-safe coordination glue for local LLM inference engines.

Rules:
- Do not commit API keys, tokens, hostnames that imply public access, or private model credentials.
- Keep examples generic and configurable through environment variables.
- Streaming behavior is critical: locks must be held until the upstream stream closes.
- Favor conservative GPU handoff over fast switching. No overlapping CUDA-heavy engines by default.

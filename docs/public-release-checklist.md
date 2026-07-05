# Public release checklist

Use this before changing repository visibility.

## Must be true

- [ ] Repository name and README title match the public name.
- [ ] License is intentional.
- [ ] `SECURITY.md` is present and clear that the lock is not a sandbox.
- [ ] No live hostnames, private IPs beyond documentation examples, API keys, tokens, or personal paths appear in tracked files.
- [ ] CI is green on GitHub.
- [ ] `python3 -m pytest -q` passes locally.
- [ ] `bash -n scripts/inference-coordinator.sh examples/vllm/start-wrapper-snippet.sh` passes locally.
- [ ] ShellCheck passes in CI.
- [ ] README says when not to use this and points users to llama-swap/LiteLLM/LoxyRouter/vLLM Production Stack where appropriate.
- [ ] Examples keep real inference backends loopback/private.

## Nice before first announcement

- [ ] Add a minimal architecture diagram.
- [ ] Add one end-to-end fake-engine demo script.
- [ ] Add an install section using `/opt/inferlock` or another neutral path.
- [ ] Add a sample config file if the shell/env contract grows.
- [ ] Add stream-cancellation and prepare-failure tests beyond the current happy path.

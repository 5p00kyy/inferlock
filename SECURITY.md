# Security

This project is coordination glue, not a sandbox or security boundary.

The lock prevents cooperating inference wrappers from overlapping GPU-heavy work. It does not stop a malicious process, a misconfigured service, or a user with shell access from bypassing the lock and talking directly to CUDA or a private backend port.

## Operator responsibilities

- Keep real inference backends loopback-only or otherwise private.
- Expose only the coordinated proxy/router ports to clients.
- Store API keys in files or service secrets, not in scripts or unit files.
- Treat configured shell commands as trusted operator configuration.
- Run the coordinator and engine services with the least privileges practical for your setup.

## Reporting

If this repo is public and you find a security issue, open a private advisory if GitHub advisories are enabled. Otherwise contact the maintainer privately before publishing details.

#!/usr/bin/env python3
import os
import sys
import time

log_path = os.environ["FAKE_ENGINE_LOG"]
name = os.environ.get("FAKE_ENGINE_NAME", str(os.getpid()))
delay = float(os.environ.get("FAKE_ENGINE_DELAY", "0.15"))

with open(log_path, "a", encoding="utf-8") as log:
    print(f"start {name} {time.monotonic():.6f}", file=log, flush=True)
    time.sleep(delay)
    print(f"end {name} {time.monotonic():.6f}", file=log, flush=True)

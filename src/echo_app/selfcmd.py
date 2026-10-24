"""How to launch Echo's own subcommands as separate processes (recorder, worker)."""

from __future__ import annotations

import os
import sys

from . import paths


def command(*args: str) -> list[str]:
    # -P: never put the current directory on sys.path.
    return [sys.executable, "-P", "-m", "echo_app", *args]


def env() -> dict[str, str]:
    e = dict(os.environ)
    e["PYTHONPATH"] = str(paths.repo_root() / "src")
    e.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    return e

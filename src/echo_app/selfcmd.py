"""How to launch Echo's own subcommands as separate processes (recorder, worker)."""

from __future__ import annotations

import os
import sys

from . import paths


def interpreter() -> str:
    """On Windows the windowless pythonw.exe, so background processes never open a console."""
    if os.name == "nt":
        w = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(w):
            return w
    return sys.executable


def command(*args: str) -> list[str]:
    # -P: never put the current directory on sys.path.
    return [interpreter(), "-P", "-m", "echo_app", *args]


def env() -> dict[str, str]:
    e = dict(os.environ)
    e["PYTHONPATH"] = str(paths.repo_root() / "src")
    e.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    return e

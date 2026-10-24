"""XDG locations. Every path can be overridden with ECHO_* environment variables (tests)."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / fallback


def config_dir() -> Path:
    if v := os.environ.get("ECHO_CONFIG_DIR"):
        return Path(v)
    return _xdg("XDG_CONFIG_HOME", ".config") / "echo"


def state_dir() -> Path:
    """Logs and runtime state that is not user data."""
    if v := os.environ.get("ECHO_STATE_DIR"):
        return Path(v)
    return _xdg("XDG_STATE_HOME", ".local/state") / "echo"


def default_data_dir() -> Path:
    if v := os.environ.get("ECHO_DATA_DIR"):
        return Path(v)
    return _xdg("XDG_DATA_HOME", ".local/share") / "echo"


def runtime_dir() -> Path:
    """Sockets and locks. Falls back to the state dir if XDG_RUNTIME_DIR is unset."""
    if v := os.environ.get("ECHO_RUNTIME_DIR"):
        path = Path(v)
    else:
        base = os.environ.get("XDG_RUNTIME_DIR")
        path = Path(base) / "echo" if base else state_dir() / "run"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

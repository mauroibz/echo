"""Crash-safe file helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via temp file + fsync + rename, so readers see old or new content, never partial."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.fchmod(fd, 0o666 & ~_umask())
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    fsync_dir(path.parent)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fsync_path(path: Path) -> None:
    """Flush a file another process is writing (fsync applies to the inode, not the fd)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def free_bytes(path: Path) -> int:
    path = Path(path)
    while not path.exists():
        path = path.parent
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def flock_with_retry(path: Path, seconds: float = 2.0):
    """Open and exclusively flock `path`, retrying briefly.

    Status checks take the same lock for an instant; retrying keeps a starting process from
    mistaking such a check for a real owner. Returns the open file, or None if still held.
    """
    import fcntl
    import time

    f = open(path, "a+")
    deadline = time.monotonic() + seconds
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except BlockingIOError:
            if time.monotonic() >= deadline:
                f.close()
                return None
            time.sleep(0.05)

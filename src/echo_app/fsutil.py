"""Crash-safe file helpers."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def fsync_dir(path: Path) -> None:
    """Make a rename in `path` durable. Windows cannot open a folder for fsync, and NTFS journals
    the rename itself, so there it is a no-op."""
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes, mkdir: bool = False) -> None:
    """Write via temp file + fsync + rename, so readers see old or new content, never partial.

    Parent folders are created only with mkdir=True, so a write can never resurrect a deleted
    recording folder.
    """
    path = Path(path)
    if mkdir:
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


def atomic_write_text(path: Path, text: str, mkdir: bool = False) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mkdir=mkdir)


def atomic_write_json(path: Path, obj: Any, mkdir: bool = False) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", mkdir=mkdir)


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
    return shutil.disk_usage(path).free  # statvfs on POSIX, GetDiskFreeSpaceEx on Windows

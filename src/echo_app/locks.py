"""Exclusive, non-blocking file locks that die with their process (stdlib only).

POSIX uses ``flock``. Windows uses ``msvcrt.locking`` on one byte far past the end of the file:
locking byte 0 would also stop other processes from reading the JSON payload some lock files
carry (the worker's lock says which folder it serves).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

_WINDOWS_OFFSET = 1 << 30


class Lock:
    """An open, locked file. Closing it (or the process ending) releases the lock."""

    def __init__(self, f):
        self.file = f

    def write_payload(self, text: str) -> None:
        self.file.seek(0)
        self.file.truncate()
        self.file.write(text)
        self.file.flush()

    def close(self) -> None:
        if not self.file.closed:
            _unlock(self.file)
            self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


if os.name == "nt":  # pragma: no cover - exercised on Windows CI
    import msvcrt

    def _try(f) -> bool:
        pos = f.tell()
        try:
            f.seek(_WINDOWS_OFFSET)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
        finally:
            f.seek(pos)

    def _unlock(f) -> None:
        try:
            f.seek(_WINDOWS_OFFSET)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _try(f) -> bool:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock(f) -> None:
        pass  # closing the file releases a flock


def acquire(path: Path, wait: float = 0.0) -> Lock | None:
    """Lock `path` (created if missing), retrying for up to `wait` seconds. None if held.

    Status checks take the same lock for an instant; retrying keeps a starting process from
    mistaking such a check for a real owner.
    """
    f = open(path, "a+", encoding="utf-8")
    deadline = time.monotonic() + wait
    while True:
        if _try(f):
            return Lock(f)
        if time.monotonic() >= deadline:
            f.close()
            return None
        time.sleep(0.05)


def holder_payload(path: Path) -> str | None:
    """The payload of a lock someone else holds, or None if nobody holds it."""
    lock = acquire(path)
    if lock is not None:
        lock.close()
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""

"""Queue transcriptions and make sure a worker is running (stdlib only; safe for the UI)."""

from __future__ import annotations

import fcntl
import os
import subprocess

import json
from pathlib import Path

from . import features, paths, selfcmd, settings
from .library import Library, Recording


def lock_path() -> Path:
    return paths.runtime_dir() / "worker.lock"


def _wanted_path() -> Path:
    return paths.runtime_dir() / "worker.wanted"


def worker_info() -> dict | None:
    """{"pid", "data_dir"} of the running worker, or None if no worker runs."""
    try:
        f = open(lock_path(), "a+")
    except OSError:
        return None
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        try:
            return json.loads(f.read() or "{}") or {"pid": None, "data_dir": None}
        except ValueError:
            return {"pid": None, "data_dir": None}
    finally:
        f.close()
    return None


def worker_running(lib: Library) -> bool:
    """True if a worker serves this library's folder."""
    info = worker_info()
    return info is not None and info.get("data_dir") in (None, str(lib.data_dir))


def wanted_dir() -> str | None:
    try:
        return _wanted_path().read_text().strip() or None
    except OSError:
        return None


def ensure_worker(lib: Library) -> bool:
    """Start the worker if it is not running. Returns False if transcription is not installed.

    If a worker is busy with another recordings folder, leave a note so it hands over when idle.
    """
    if not features.transcription_installed():
        return False
    if os.environ.get("ECHO_NO_WORKER"):  # tests queue work without starting GPU processes
        return True
    info = worker_info()
    if info is not None:
        if info.get("data_dir") not in (None, str(lib.data_dir)):
            _wanted_path().write_text(str(lib.data_dir))
        return True
    if wanted_dir() == str(lib.data_dir):
        _wanted_path().unlink(missing_ok=True)
    subprocess.Popen(selfcmd.command("_worker", "--data-dir", str(lib.data_dir)), env=selfcmd.env(),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)
    return True


def request(lib: Library, rec: Recording, adapter: bool | None = None) -> bool:
    if adapter is None:
        cfg, _ = settings.load()
        adapter = cfg.use_adapter
    rec.request_transcription(adapter=adapter)
    return ensure_worker(lib)


def cancel(rec: Recording) -> None:
    rec.cancel_transcription()


def resume_pending(lib: Library) -> int:
    """Start the worker if any recording is waiting (e.g. after a restart). Returns the count."""
    from .library import REQUESTED

    n = sum(1 for rec in lib.all() if rec.path(REQUESTED).exists())
    if n:
        ensure_worker(lib)
    return n

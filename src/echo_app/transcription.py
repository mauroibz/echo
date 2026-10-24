"""Queue transcriptions and make sure a worker is running (stdlib only; safe for the UI)."""

from __future__ import annotations

import fcntl
import subprocess

from . import features, selfcmd, settings
from .library import Library, Recording

LOCK = ".worker.lock"


def worker_running(lib: Library) -> bool:
    try:
        f = open(lib.data_dir / LOCK, "a+")
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        f.close()
    return False


def ensure_worker(lib: Library) -> bool:
    """Start the worker if it is not running. Returns False if transcription is not installed."""
    if not features.transcription_installed():
        return False
    if not worker_running(lib):
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

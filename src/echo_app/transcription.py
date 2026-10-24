"""Queue transcriptions and make sure a worker is running (stdlib only; safe for the UI)."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

from . import features, paths, selfcmd, settings
from .fsutil import atomic_write_json, read_json
from .library import Library, Recording

SPEED_JOBS = 10  # the speed estimate averages this many recent jobs
# Before the first job on a machine: minutes of work per hour of audio, measured on the
# reference machines in docs/design.md (an RTX 3080; a 6-core Ryzen 5 7600X for the CPU).
EXPECTED_MIN_PER_HOUR = {features.CUDA: 1.0, features.CPU: 5.0}


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


def build_context(rec: Recording, line: str | None = None) -> str:
    """The context sentence for a job: the recording's own line, then the dictionary's entries.

    The entries it names are marked as used, so the dictionary keeps the active ones in the
    sentence when it grows beyond the budget.
    """
    from . import dictionary

    d = dictionary.load()
    text, included = dictionary.context_sentence(d, rec.meta.context_line if line is None else line)
    if included:
        d.touch(included)
        try:
            d.save()
        except OSError:
            pass
    return text


def request(lib: Library, rec: Recording, adapter: bool | None = None, context: str | None = None,
            start_worker: bool = True) -> bool:
    """Queue a transcription. `context` replaces the recording's context line for this job."""
    if adapter is None:
        cfg, _ = settings.load()
        adapter = cfg.use_adapter
    options = {"adapter": adapter}
    sentence = build_context(rec, context)
    if sentence:
        options["context"] = sentence
    rec.request_transcription(**options)
    return ensure_worker(lib) if start_worker else features.transcription_installed()


def cancel(rec: Recording) -> None:
    rec.cancel_transcription()


def resume_pending(lib: Library) -> int:
    """Start the worker if any recording is waiting (e.g. after a restart). Returns the count."""
    from .library import REQUESTED

    n = sum(1 for rec in lib.all() if rec.path(REQUESTED).exists())
    if n:
        ensure_worker(lib)
    return n


# ---- measured speed ----------------------------------------------------------------------------

def speed_path() -> Path:
    return paths.state_dir() / "speed.json"


def speed_key(device: str, profile: str | None = None) -> str:
    """"cpu" whenever the model ran on the processor (also a GPU profile without a GPU)."""
    return features.CPU if device == "cpu" else (profile or features.compute_profile())


def record_speed(key: str, audio_s: float, elapsed_s: float) -> None:
    """Called by the worker after each job: seconds of audio and of work, model load included."""
    if audio_s <= 0 or elapsed_s <= 0:
        return
    try:
        data = read_json(speed_path())
    except (OSError, ValueError):
        data = {}
    jobs = (data.get(key) or {}).get("jobs", [])[-(SPEED_JOBS - 1):]
    jobs.append([round(audio_s, 1), round(elapsed_s, 1), round(time.time())])
    data[key] = {"jobs": jobs}
    try:
        atomic_write_json(speed_path(), data, mkdir=True)
    except OSError:
        pass


def minutes_per_hour(key: str | None = None) -> tuple[float | None, bool]:
    """(minutes of work per hour of audio, measured on this computer?) for the installed profile."""
    if key is None:
        profile = features.compute_profile()
        on_cpu = profile == features.CPU or features.detected_hardware() == features.CPU
        key = features.CPU if on_cpu else profile
    try:
        jobs = (read_json(speed_path()).get(key) or {}).get("jobs", [])
    except (OSError, ValueError, AttributeError):
        jobs = []
    audio = sum(j[0] for j in jobs)
    work = sum(j[1] for j in jobs)
    if audio >= 60:
        return work / audio * 60, True
    return EXPECTED_MIN_PER_HOUR.get(key), False


def speed_text() -> str:
    """"About 6 minutes per hour of audio on this computer", or "" when nothing is known."""
    minutes, measured = minutes_per_hour()
    if minutes is None:
        return ""
    amount = "less than a minute" if minutes < 1.5 else f"about {round(minutes)} minutes"
    return f"Transcription takes {amount} per hour of audio {'on this computer' if measured else 'on a typical computer'}."

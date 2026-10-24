"""Crash-safe recording engine (stdlib only).

Three processes, each able to die alone without losing captured audio:

* the UI or CLI, which starts a recording and sends it signals;
* the supervisor (``echo-app _recorder <id>``), which owns one recording: it starts capture
  takes, flushes them to disk every two seconds, restarts capture after interruptions and
  finalizes into verified FLAC on stop;
* the capture process (``pw-record``), which writes raw PCM to ``takes/take-NNN.raw``.

Both the supervisor and the capture run in their own sessions, so closing the window or the
terminal does not reach them. ``recover_all`` repairs whatever a crash left behind.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import select
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import features, selfcmd
from .audio import ffmpeg, pipewire
from .fsutil import atomic_write_json, free_bytes, fsync_dir, fsync_path, read_json
from .library import NEEDS_FINALIZE, READY, RECORDING, Library, Recording

log = logging.getLogger(__name__)

SESSION = "session.json"
STATUS = "status.json"
LOCK = ".recorder.lock"

FSYNC_EVERY = 2.0
TICK = 0.25
STATUS_EVERY = 0.5
STALL_AFTER = 3.0
START_GRACE = 3.0
SOURCE_CHECK_EVERY = 5.0
DISK_CHECK_EVERY = 5.0
MIN_FREE_TO_START = 1_000_000_000
FLAC_RATIO = 0.6  # FLAC needs up to this fraction of the raw size while finalizing
DISK_MARGIN = 100_000_000
FAILS_BEFORE_DEFAULT = 3

# Session states (also shown in status.json)
S_STARTING = "starting"
S_RECORDING = "recording"
S_PAUSED = "paused"
S_FINALIZING = "finalizing"
S_DONE = "done"
S_ERROR = "error"


class RecorderError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------------------------

def _cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [p.decode(errors="replace") for p in f.read().split(b"\0") if p]
    except OSError:
        return []


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers kill(0); treat it as dead.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def supervisor_matches(pid: int | None, rec_id: str) -> bool:
    cmd = _cmdline(pid) if pid else []
    return _alive(pid) and "_recorder" in cmd and rec_id in cmd


def capture_matches(pid: int | None, take_path: Path) -> bool:
    cmd = _cmdline(pid) if pid else []
    return _alive(pid) and str(take_path) in cmd


def capture_cmd(source: pipewire.Source | None, rate: int, channels: int, path: Path) -> list[str]:
    """The capture command. ECHO_CAPTURE_CMD replaces it in tests ({path}, {bps} placeholders)."""
    template = os.environ.get("ECHO_CAPTURE_CMD")
    if template:
        bps = rate * channels * 2
        return [part.format(path=str(path), bps=bps) for part in shlex.split(template)]
    return pipewire.record_cmd(source, rate, channels, str(path))


def _fake_capture() -> bool:
    return bool(os.environ.get("ECHO_CAPTURE_CMD"))


class Capture:
    """A running capture process, either our child or adopted from a dead supervisor."""

    def __init__(self, pid: int, path: Path, popen: subprocess.Popen | None = None):
        self.pid = pid
        self.path = path
        self.popen = popen

    def alive(self) -> bool:
        if self.popen is not None:
            return self.popen.poll() is None
        return capture_matches(self.pid, self.path)

    def stop(self, timeout: float = 3.0) -> None:
        """SIGINT lets pw-record flush its buffer; escalate only if it hangs."""
        for sig, wait in ((signal.SIGINT, timeout), (signal.SIGKILL, 2.0)):
            if not self.alive():
                return
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                if self.popen is not None:
                    try:
                        self.popen.wait(timeout=0.05)
                        return
                    except subprocess.TimeoutExpired:
                        continue
                if not self.alive():
                    return
                time.sleep(0.05)


# ---------------------------------------------------------------------------------------------
# Session files
# ---------------------------------------------------------------------------------------------

def session_path(rec: Recording) -> Path:
    return rec.takes_dir / SESSION


def load_session(rec: Recording) -> dict[str, Any] | None:
    try:
        return read_json(session_path(rec))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_status(rec: Recording) -> dict[str, Any] | None:
    try:
        return read_json(rec.takes_dir / STATUS)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_status(rec: Recording, status: dict[str, Any]) -> None:
    # Best-effort heartbeat: atomic rename without fsync (losing one on power cut is harmless).
    tmp = rec.takes_dir / f".{STATUS}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(status, f)
        os.replace(tmp, rec.takes_dir / STATUS)
    except OSError:
        pass


def take_files(rec: Recording) -> list[Path]:
    return sorted(rec.takes_dir.glob("take-*.raw"))


def recorded_bytes(rec: Recording) -> int:
    total = 0
    for p in take_files(rec):
        try:
            total += p.stat().st_size
        except FileNotFoundError:
            pass
    return total


# ---------------------------------------------------------------------------------------------
# Locking: one active recording per data directory
# ---------------------------------------------------------------------------------------------

def _lock_path(lib: Library) -> Path:
    return lib.data_dir / LOCK


def try_lock(lib: Library):
    """Return an open, flock'ed file object, or None if another recorder holds it."""
    f = open(_lock_path(lib), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


# ---------------------------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------------------------

class Supervisor:
    def __init__(self, lib: Library, rec: Recording, adopt: bool = False):
        self.lib = lib
        self.rec = rec
        self.adopt = adopt
        self.session: dict[str, Any] = {}
        self.capture: Capture | None = None
        self.source: pipewire.Source | None = None
        self.state = S_STARTING
        self.warning: str | None = None
        self._flags: set[str] = set()
        self._take_started = 0.0
        self._last_size = -1
        self._last_growth = 0.0
        self._fails = 0
        self._source_missing = False
        self._next_retry = 0.0
        self._warning_expires = 0.0

    # ---- signals ----
    def _on_signal(self, signum, _frame):
        self._flags.add({signal.SIGTERM: "stop", signal.SIGINT: "stop",
                         signal.SIGUSR1: "pause", signal.SIGUSR2: "resume"}[signum])

    def _install_signals(self):
        # The wakeup pipe makes the main loop react to a signal immediately instead of on the
        # next tick.
        self._wake_r, wake_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        signal.set_wakeup_fd(wake_w)
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1, signal.SIGUSR2):
            signal.signal(s, self._on_signal)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def _sleep(self, seconds: float):
        r, _, _ = select.select([self._wake_r], [], [], seconds)
        if r:
            try:
                while os.read(self._wake_r, 512):
                    pass
            except BlockingIOError:
                pass

    # ---- persistence ----
    def _save_session(self):
        self.session["state"] = self.state
        atomic_write_json(session_path(self.rec), self.session)

    @property
    def rate(self) -> int:
        return self.session["rate"]

    @property
    def channels(self) -> int:
        return self.session["channels"]

    @property
    def bps(self) -> int:
        return self.rate * self.channels * 2

    def elapsed(self) -> float:
        return recorded_bytes(self.rec) / self.bps

    def _note(self, cause: str, seconds: float | None = None, kind: str = "interruption"):
        entry = {"at": round(self.elapsed(), 2), "wall": _now_iso(), "cause": cause, "kind": kind}
        if seconds is not None:
            entry["seconds"] = round(seconds, 2)
        self.session.setdefault("events", []).append(entry)
        log.info("%s: %s", self.rec.id, cause)
        self._save_session()

    def _status(self):
        cur = self.capture.path.name if self.capture else None
        _write_status(self.rec, {
            "state": self.state, "elapsed": round(self.elapsed(), 2), "take": cur,
            "rate": self.rate, "channels": self.channels, "warning": self.warning,
            "source": self.session.get("source_label"), "supervisor_pid": os.getpid(),
            "updated": time.time(),
        })

    # ---- takes ----
    def _start_take(self) -> bool:
        n = len(take_files(self.rec)) + 1
        path = self.rec.takes_dir / f"take-{n:03d}.raw"
        while path.exists():
            n += 1
            path = self.rec.takes_dir / f"take-{n:03d}.raw"
        path.touch()
        cmd = capture_cmd(self.source, self.rate, self.channels, path)
        logf = open(path.with_suffix(".log"), "ab")
        try:
            popen = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=logf, start_new_session=True, close_fds=True)
        except OSError as e:
            logf.close()
            self.warning = f"Could not start capture: {e}"
            log.error(self.warning)
            return False
        finally:
            if not logf.closed:
                logf.close()
        self.capture = Capture(popen.pid, path, popen)
        self.session.setdefault("takes", []).append({
            "file": path.name, "pid": popen.pid, "started": _now_iso(),
            "source": self.source.name if self.source else None, "ended": None, "end_reason": None})
        fsync_dir(self.rec.takes_dir)
        now = time.monotonic()
        self._take_started = now
        self._last_size = 0
        self._last_growth = now
        self._save_session()
        return True

    def _end_take(self, reason: str):
        if not self.capture:
            return
        self.capture.stop()
        path = self.capture.path
        fsync_path(path)
        takes = self.session.get("takes", [])
        empty = path.exists() and path.stat().st_size == 0
        if empty:
            # A take that never produced audio carries nothing; keep its error in the log only.
            logf = path.with_suffix(".log")
            try:
                err = logf.read_text(errors="replace").strip()
            except OSError:
                err = ""
            if err:
                log.warning("%s: capture produced no audio: %s", self.rec.id, err[-500:])
            path.unlink(missing_ok=True)
            logf.unlink(missing_ok=True)
            self.session["takes"] = [t for t in takes if t["file"] != path.name]
        else:
            for t in reversed(takes):
                if t["file"] == path.name:
                    t["ended"], t["end_reason"] = _now_iso(), reason
                    break
        self.capture = None
        self._save_session()

    def _restart(self, cause: str):
        produced = self.capture is not None and self.capture.path.exists() and self.capture.path.stat().st_size > 0
        if not produced:
            # Capture fails before any audio: back off instead of spinning, and say so once.
            self._fails += 1
            self._end_take("failed")
            delay = min(5.0, 0.5 * 2 ** (self._fails - 1))
            self._next_retry = time.monotonic() + delay
            if self._fails == FAILS_BEFORE_DEFAULT and self.source is not None and not _fake_capture():
                fallback = pipewire.default_source()
                if fallback and fallback.name != self.source.name:
                    self.source = fallback
                    self.session["source_label"] = fallback.label
                    self._note(f"Could not capture from the selected input; switched to {fallback.label}")
            if self._fails == 1:
                log.warning("%s: no audio from the input; retrying", self.rec.id)
            self.warning = "No audio from the input. Retrying..."
            self._warning_expires = 0.0
            return
        self._note(cause)
        self._end_take("interrupted")
        self.warning = "Capture was interrupted and restarted. Check the input device."
        self._warning_expires = time.monotonic() + 15.0
        if not self._start_take():
            self._next_retry = time.monotonic() + 2.0

    # ---- checks ----
    def _check_capture(self, now: float):
        if self.capture is None:
            if now >= self._next_retry:
                if not self._start_take():
                    self._next_retry = now + 2.0
            return
        try:
            size = self.capture.path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size != self._last_size:
            if size > 0 and self._last_size <= 0:
                self._fails = 0
                if self.warning and self.warning.startswith("No audio"):
                    self.warning = None
            self._last_size = size
            self._last_growth = now
        if self._warning_expires and now > self._warning_expires:
            self.warning = None
            self._warning_expires = 0.0
        if not self.capture.alive():
            if self._last_size > 0:
                self._restart("Capture stopped unexpectedly; restarted")
            else:
                self._restart("")
        elif now - self._take_started > START_GRACE and now - self._last_growth > STALL_AFTER:
            self._restart("Capture stalled; restarted" if self._last_size > 0 else "")

    def _check_source(self):
        if _fake_capture() or self.source is None:
            return
        present = pipewire.find(self.source.name) is not None
        if not present and not self._source_missing:
            self._source_missing = True
            self.warning = f"{self.source.label} disconnected; recording from the default input"
            self._note(f"{self.source.label} disconnected; PipeWire continued from the default input")
        elif present and self._source_missing:
            self._source_missing = False
            self.warning = None
            self._note(f"{self.source.label} reconnected", kind="info")

    def _check_disk(self) -> bool:
        """Return False when recording must stop for lack of space."""
        free = free_bytes(self.lib.data_dir)
        reserve = int(recorded_bytes(self.rec) * FLAC_RATIO) + DISK_MARGIN
        if free < reserve:
            self._note("Disk almost full; recording stopped")
            return False
        minutes_left = (free - reserve) / self.bps / 60
        if minutes_left < 10:
            self.warning = f"Disk space low: about {minutes_left:.0f} minutes of recording left"
        return True

    # ---- lifecycle ----
    def _setup_new(self):
        meta = self.rec.meta
        self.session = load_session(self.rec) or {}
        self.session.setdefault("version", 1)
        self.session.setdefault("rate", meta.sample_rate or 48000)
        self.session.setdefault("channels", meta.channels or 1)
        self.session.setdefault("events", [])
        self.session.setdefault("takes", [])
        self.session["supervisor_pid"] = os.getpid()
        wanted = self.session.get("source")
        if _fake_capture():
            self.source = pipewire.Source(wanted or "fake", "Test source", pipewire.INPUT, is_default=True)
            self.session["source_label"] = self.source.label
        else:
            self.source, note = pipewire.resolve(wanted or "")
            self.session["source_label"] = self.source.label if self.source else "System default input"
            if note:
                self.warning = note
                self.session["events"].append({"at": 0.0, "wall": _now_iso(), "cause": note, "kind": "info"})

    def _setup_adopt(self):
        self.session = load_session(self.rec) or {}
        if not self.session:
            raise RecorderError("no session to adopt")
        self.session["supervisor_pid"] = os.getpid()
        name = None
        for t in self.session.get("takes", []):
            name = t.get("source") or name
        if _fake_capture():
            self.source = pipewire.Source(name or "fake", "Test source", pipewire.INPUT, is_default=True)
        else:
            self.source = pipewire.find(name) if name else None
        last = (self.session.get("takes") or [None])[-1]
        if last and last.get("ended") is None:
            path = self.rec.takes_dir / last["file"]
            if capture_matches(last.get("pid"), path):
                self.capture = Capture(last["pid"], path)
                now = time.monotonic()
                self._take_started = now
                self._last_size = path.stat().st_size if path.exists() else 0
                self._last_growth = now
        self._note("Recorder restarted after a crash; capture continued", kind="info")

    def run(self) -> int:
        lock = try_lock(self.lib)
        if lock is None:
            log.error("another recording is active; supervisor for %s exiting", self.rec.id)
            if not self.adopt and recorded_bytes(self.rec) == 0:
                shutil.rmtree(self.rec.folder, ignore_errors=True)
            return 3
        self._install_signals()
        try:
            if self.adopt:
                self._setup_adopt()
                self.state = S_PAUSED if self.session.get("state") == S_PAUSED and not self.capture else S_RECORDING
                if self.state == S_RECORDING and not self.capture:
                    self._start_take()
            else:
                self._setup_new()
                self.state = S_RECORDING
                if not self._start_take():
                    self._next_retry = time.monotonic() + 2.0
            self._save_session()
            return self._loop()
        finally:
            lock.close()

    def _loop(self) -> int:
        last_fsync = last_status = last_source = last_disk = 0.0
        paused_at = None
        while True:
            now = time.monotonic()
            if "stop" in self._flags:
                break
            if "pause" in self._flags:
                self._flags.discard("pause")
                if self.state == S_RECORDING:
                    self._end_take("paused")
                    self.state = S_PAUSED
                    paused_at = now
                    self._save_session()
                    self._status()
            if "resume" in self._flags:
                self._flags.discard("resume")
                if self.state == S_PAUSED:
                    self.state = S_RECORDING
                    seconds = now - paused_at if paused_at else None
                    self._note("Paused", seconds=seconds, kind="pause")
                    paused_at = None
                    if not self._start_take():
                        self._next_retry = now + 2.0
                    self._status()
            if self.state == S_RECORDING:
                self._check_capture(now)
                if now - last_fsync >= FSYNC_EVERY and self.capture:
                    fsync_path(self.capture.path)
                    last_fsync = now
                if now - last_source >= SOURCE_CHECK_EVERY:
                    self._check_source()
                    last_source = now
                if now - last_disk >= DISK_CHECK_EVERY:
                    last_disk = now
                    if not self._check_disk():
                        break
            if now - last_status >= STATUS_EVERY:
                self._status()
                last_status = now
            self._sleep(TICK)
        if self.state == S_PAUSED and paused_at:
            self._note("Paused", seconds=time.monotonic() - paused_at, kind="pause")
        self._end_take("stopped")
        self.state = S_FINALIZING
        self._save_session()
        self._status()
        outcome = finalize(self.rec)
        return 0 if outcome in ("ready", "empty") else 1


# ---------------------------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------------------------

def finalize(rec: Recording, recovered: bool = False) -> str:
    """Turn raw takes into verified FLAC. Returns 'ready', 'empty' or 'failed'."""
    session = load_session(rec) or {}
    rate = session.get("rate") or rec.meta.sample_rate or 48000
    channels = session.get("channels") or rec.meta.channels or 1
    takes = take_files(rec)
    frame = 2 * channels
    total = sum(p.stat().st_size // frame * frame for p in takes)
    if total == 0:
        log.info("%s: no audio captured, removing", rec.id)
        shutil.rmtree(rec.folder, ignore_errors=True)
        return "empty"
    if rec.meta.state == READY and rec.audio_path and rec.audio_path.exists():
        shutil.rmtree(rec.takes_dir, ignore_errors=True)  # crashed after finalize, before cleanup
        return "ready"
    partial = rec.folder / "audio.flac.partial"
    final = rec.folder / "audio.flac"
    try:
        frames = ffmpeg.encode_flac_verified(takes, rate, channels, partial)
        fsync_path(partial)
        os.replace(partial, final)
        fsync_dir(rec.folder)
    except (ffmpeg.FFmpegError, OSError) as e:
        log.error("%s: finalize failed: %s", rec.id, e)
        rec.update(state=NEEDS_FINALIZE, error=f"Saving the recording failed: {e}", sample_rate=rate,
                   channels=channels)
        return "failed"
    events = session.get("events", [])
    rec.update(state=READY, audio=final.name, sha256=ffmpeg.sha256_file(final),
               duration=round(frames / rate, 3), sample_rate=rate, channels=channels,
               recovered=recovered or rec.meta.recovered, gaps=events, error=None)
    shutil.rmtree(rec.takes_dir, ignore_errors=True)
    fsync_dir(rec.folder)
    log.info("%s: finalized %.1f s", rec.id, frames / rate)
    try:
        if features.auto_transcribe() and rec.transcript_status() == "none":
            from . import transcription

            transcription.request(Library(rec.folder.parent.parent), rec)
    except OSError:
        log.exception("could not queue transcription for %s", rec.id)
    return "ready"


# ---------------------------------------------------------------------------------------------
# Control API for the UI and CLI
# ---------------------------------------------------------------------------------------------

@dataclass
class Session:
    rec: Recording

    def info(self) -> dict[str, Any]:
        return load_session(self.rec) or {}

    def status(self) -> dict[str, Any]:
        st = read_status(self.rec) or {}
        if not st:
            info = self.info()
            st = {"state": info.get("state", S_STARTING), "elapsed": 0.0,
                  "rate": info.get("rate", 48000), "channels": info.get("channels", 1)}
        if st.get("state") not in (S_FINALIZING, S_DONE):
            st["elapsed"] = recorded_bytes(self.rec) / (st.get("rate", 48000) * st.get("channels", 1) * 2)
        return st

    @property
    def supervisor_pid(self) -> int | None:
        return self.info().get("supervisor_pid")

    def alive(self) -> bool:
        return supervisor_matches(self.supervisor_pid, self.rec.id)

    def _signal(self, sig) -> None:
        pid = self.supervisor_pid
        if not supervisor_matches(pid, self.rec.id):
            raise RecorderError("The recorder for this recording is not running.")
        os.kill(pid, sig)

    def pause(self) -> None:
        self._signal(signal.SIGUSR1)

    def resume(self) -> None:
        self._signal(signal.SIGUSR2)

    def stop(self, wait: float = 0.0) -> str | None:
        """Ask the supervisor to stop. With wait > 0, block until finalized (returns outcome)."""
        self._signal(signal.SIGTERM)
        if wait <= 0:
            return None
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if not self.rec.folder.exists():
                return "empty"
            if not self.alive():
                self.rec.reload()
                return "ready" if self.rec.meta.state == READY else "failed"
            time.sleep(0.1)
        return None

    def current_take(self) -> Path | None:
        st = read_status(self.rec) or {}
        name = st.get("take")
        return self.rec.takes_dir / name if name else None


def active(lib: Library) -> Session | None:
    for rec in lib.all():
        if rec.takes_dir.is_dir() and rec.meta.state == RECORDING:
            s = Session(rec)
            if s.alive():
                return s
    return None


def start(lib: Library, source: str = "", rate: int = 48000, channels: int = 1,
          title: str | None = None, timeout: float = 5.0) -> Session:
    """Start a detached supervisor for a new recording and wait until it is capturing."""
    if (s := active(lib)) is not None:
        raise RecorderError(f"Already recording \"{s.rec.meta.title}\". Stop it first.")
    lock = try_lock(lib)
    if lock is None:
        raise RecorderError("Another recording is active. Stop it first.")
    lock.close()
    free = free_bytes(lib.data_dir)
    if free < MIN_FREE_TO_START:
        raise RecorderError(f"Only {free / 1e9:.1f} GB free in {lib.data_dir}; at least 1 GB is needed to record.")
    label = ""
    if not _fake_capture():
        src, _ = pipewire.resolve(source)
        label = src.label if src else "System default input"
    now = datetime.now()
    rec = lib.create(title or f"Recording {now:%Y-%m-%d %H:%M}", "recorded", state=RECORDING,
                     source=label, sample_rate=rate, channels=channels)
    rec.takes_dir.mkdir()
    atomic_write_json(session_path(rec), {"version": 1, "rate": rate, "channels": channels,
                                          "source": source or None, "state": S_STARTING,
                                          "events": [], "takes": [], "created": _now_iso()})
    _spawn_supervisor(rec)
    sess = Session(rec)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = read_status(rec)
        if st and st.get("state") == S_RECORDING:
            return sess
        if not rec.folder.exists():
            raise RecorderError("The recorder exited immediately (another recording may be active).")
        time.sleep(0.05)
    if sess.alive():
        return sess
    raise RecorderError("The recorder did not start. See the log in ~/.local/state/echo/.")


def _spawn_supervisor(rec: Recording, adopt: bool = False) -> subprocess.Popen:
    args = ["_recorder", rec.id, "--data-dir", str(rec.folder.parent.parent)]
    args += ["--adopt"] if adopt else []
    return subprocess.Popen(selfcmd.command(*args), env=selfcmd.env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, close_fds=True)


# ---------------------------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------------------------

def recover_all(lib: Library) -> list[tuple[str, str]]:
    """Repair recordings left behind by crashes. Returns [(recording id, action)]."""
    actions = []
    for rec in lib.all():
        try:
            action = recover_one(lib, rec)
        except Exception as e:  # noqa: BLE001 - one broken folder must not block the rest
            log.exception("recovery of %s failed", rec.id)
            action = f"failed: {e}"
        if action:
            actions.append((rec.id, action))
    return actions


def recover_one(lib: Library, rec: Recording) -> str | None:
    has_takes = rec.takes_dir.is_dir()
    if not has_takes:
        if rec.meta.state == RECORDING:
            # Crash before any take existed, or after cleanup but before the meta update.
            audio = rec.folder / "audio.flac"
            if audio.exists():
                p = ffmpeg.probe(audio)
                rec.update(state=READY, audio=audio.name, duration=p.duration, recovered=True,
                           sha256=ffmpeg.sha256_file(audio))
                return "finalized"
            shutil.rmtree(rec.folder, ignore_errors=True)
            return "empty"
        return None
    sess = Session(rec)
    if sess.alive():
        return "live"
    session = load_session(rec) or {}
    last = (session.get("takes") or [None])[-1]
    if last and last.get("ended") is None and capture_matches(last.get("pid"), rec.takes_dir / last["file"]):
        _spawn_supervisor(rec, adopt=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not sess.alive():
            time.sleep(0.05)
        return "adopted"
    if rec.meta.state == READY and rec.audio_path and rec.audio_path.exists():
        shutil.rmtree(rec.takes_dir, ignore_errors=True)
        return "cleaned"
    outcome = finalize(rec, recovered=rec.meta.state == RECORDING)
    return {"ready": "finalized", "empty": "empty", "failed": "failed"}[outcome]


def supervisor_main(rec_id: str, data_dir: str, adopt: bool) -> int:
    lib = Library(Path(data_dir))
    rec = lib.get(rec_id)
    if rec is None:
        log.error("supervisor: no recording %s", rec_id)
        return 2
    try:
        return Supervisor(lib, rec, adopt=adopt).run()
    except Exception:
        log.exception("supervisor for %s crashed", rec_id)
        raise



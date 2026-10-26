"""Crash-safe recording engine (stdlib only).

Three processes, each able to die alone without losing captured audio:

* the UI or CLI, which starts a recording and controls it with command files;
* the supervisor (``echo-app _recorder <id>``), which owns one recording: it starts capture
  takes, flushes them to disk every two seconds, restarts capture after interruptions and
  finalizes into verified FLAC on stop;
* the capture (``pw-record`` through the audio backend), which writes raw PCM to
  ``takes/take-NNN.raw``. A call recording has a second capture of the computer audio writing
  ``takes/out-NNN.raw``; the two start and stop together, as a pair (see audio/tracks.py).

Both the supervisor and the capture run in their own sessions, so closing the window or the
terminal does not reach them. The window and the CLI find a running recording from its files
alone: ``session.json`` names the supervisor and a random token, and ``status.json`` carries the
same token and a heartbeat twice a second. Commands (pause, resume, stop) are small files in
``takes/commands/``, read by the supervisor on every tick. ``recover_all`` repairs whatever a
crash left behind.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import features, locks, selfcmd
from .audio import backend, ffmpeg, tracks
from .audio.backend import Source
from .fsutil import atomic_write_json, free_bytes, fsync_dir, fsync_path, read_json
from .library import NEEDS_FINALIZE, READY, RECORDING, Library, Recording

log = logging.getLogger(__name__)

SESSION = "session.json"
STATUS = "status.json"
COMMANDS = "commands"
LOCK = ".recorder.lock"

FSYNC_EVERY = 2.0
TICK = 0.1  # commands are read every tick: pause and stop take effect within 0.1 s
STATUS_EVERY = 0.5
STALL_AFTER = 3.0
START_GRACE = 3.0
SOURCE_CHECK_EVERY = 5.0
DISK_CHECK_EVERY = 5.0
MIN_FREE_TO_START = 1_000_000_000
FLAC_RATIO = 0.6  # FLAC needs up to this fraction of the raw size while finalizing
DISK_MARGIN = 100_000_000
FAILS_BEFORE_DEFAULT = 3
HEARTBEAT_STALE = 3.0  # a supervisor whose status is older than this is not answering
HUNG_GRACE = 10.0  # ... and is treated as dead by recovery after this long
STARTING_GRACE = 30.0  # a new recording whose supervisor has not reported yet is left alone this long
CAPTURE_GROWING = 3.0  # a take written to within this many seconds still has a live capture

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

def pid_alive(pid: int | None) -> bool:
    """Whether a process with this pid exists. Callers confirm identity by token or file growth."""
    if not pid:
        return False
    if os.name == "nt":  # pragma: no cover
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        # A zombie (exited, not yet reaped by its parent) still answers kill(0).
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass  # not our child; its own parent reaps it
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
    # Someone else's zombie: an orphaned capture whose new parent never reaps (a container's first
    # process often does not) would otherwise look alive for good.
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat[stat.rindex(")") + 2:][:1] not in ("Z", "X")
    except (OSError, ValueError):
        return True


def take_growing(path: Path, within: float = CAPTURE_GROWING) -> bool:
    """A capture is alive if its take was written to recently (pw-record writes every 20 ms)."""
    try:
        return time.time() - path.stat().st_mtime < within
    except FileNotFoundError:
        return False


class AdoptedCapture:
    """A capture left running by a supervisor that died; recognized by its take still growing."""

    def __init__(self, pid: int | None, path: Path):
        self.pid = pid
        self.path = path

    def alive(self) -> bool:
        return take_growing(self.path) and (self.pid is None or pid_alive(self.pid)) and self._same_process()

    def _same_process(self) -> bool:
        """Where /proc exists, the pid is still the capture writing this take (pids are reused)."""
        if self.pid is None or not os.path.isdir("/proc"):
            return True
        try:
            with open(f"/proc/{self.pid}/cmdline", "rb") as f:
                return str(self.path).encode() in f.read()
        except OSError:
            return False

    def stop(self, timeout: float = 3.0) -> None:
        """SIGINT lets pw-record flush its buffer; escalate only if it hangs."""
        if self.pid is None:
            return
        for sig, wait in ((signal.SIGINT, timeout), (getattr(signal, "SIGKILL", signal.SIGTERM), 2.0)):
            if not pid_alive(self.pid) or not self._same_process():
                return
            try:
                os.kill(self.pid, sig)
            except (ProcessLookupError, OSError):
                return
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                if not pid_alive(self.pid):
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


def send_command(rec: Recording, command: str) -> None:
    """Queue a command for the supervisor: one line in its own file, so none overwrites another."""
    d = rec.takes_dir / COMMANDS
    d.mkdir(exist_ok=True)
    atomic_write_json(d / f"{time.time_ns():020d}-{secrets.token_hex(2)}.cmd", {"command": command})


def read_commands(rec: Recording) -> list[str]:
    """The queued commands, oldest first, removing each as it is read."""
    d = rec.takes_dir / COMMANDS
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".cmd"))
    except FileNotFoundError:
        return []
    out = []
    for n in names:
        try:
            out.append(str(read_json(d / n).get("command", "")))
        except (OSError, ValueError, AttributeError):
            pass
        try:
            os.unlink(d / n)
        except OSError:
            pass
    return [c for c in out if c]


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


def out_files(rec: Recording) -> list[Path]:
    """The computer-audio takes of a call recording."""
    return sorted(rec.takes_dir.glob("out-*.raw"))


def recorded_bytes(rec: Recording, files: list[Path] | None = None) -> int:
    """Bytes of input audio so far (elapsed time and markers count the input alone)."""
    total = 0
    for p in take_files(rec) if files is None else files:
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


def try_lock(lib: Library) -> locks.Lock | None:
    """The data folder's recording lock, or None if another recorder holds it."""
    return locks.acquire(_lock_path(lib))


# ---------------------------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------------------------

class Supervisor:
    def __init__(self, lib: Library, rec: Recording, adopt: bool = False):
        self.lib = lib
        self.rec = rec
        self.adopt = adopt
        self.session: dict[str, Any] = {}
        self.capture: backend.Capture | None = None
        self.out: backend.Capture | None = None  # the computer audio of a call recording
        self.take_file: str | None = None  # the current pair's input take, which names it in session.json
        self.source: Source | None = None
        self.backend = backend.get()
        self.token = secrets.token_hex(8)
        self.state = S_STARTING
        self.warning: str | None = None
        self._flags: set[str] = set()
        self._take_started = 0.0
        self._last_size = -1
        self._last_growth = 0.0
        self._out_last_size = -1
        self._out_last_growth = 0.0
        self._out_warned = False
        self._fails = 0
        self._source_missing = False
        self._next_retry = 0.0
        self._warning_expires = 0.0

    # ---- control: command files, and on POSIX the signals of earlier versions ----
    _SIGNALS = {"SIGTERM": "stop", "SIGINT": "stop", "SIGUSR1": "pause", "SIGUSR2": "resume"}

    def _on_signal(self, signum, _frame):
        self._flags.add(self._SIGNALS[signal.Signals(signum).name])

    def _install_signals(self):
        # Signals stay accepted for one release, so a recording started by the previous version
        # can still be stopped by this one. The wakeup pipe makes the loop react at once.
        self._wake_r = None
        if os.name != "nt":
            self._wake_r, wake_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
            signal.set_wakeup_fd(wake_w)
        for name in self._SIGNALS:
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), self._on_signal)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def _sleep(self, seconds: float):
        if self._wake_r is None:
            time.sleep(seconds)
            return
        import select

        r, _, _ = select.select([self._wake_r], [], [], seconds)
        if r:
            try:
                while os.read(self._wake_r, 512):
                    pass
            except BlockingIOError:
                pass

    def _read_commands(self):
        for c in read_commands(self.rec):
            word, _, arg = c.partition(" ")
            if word in ("pause", "resume", "stop"):
                self._flags.add(word)
            else:
                self._command(word, arg)

    def _command(self, word: str, arg: str) -> None:
        if word == "mark":
            # The position in the captured audio: bytes so far, so pauses and gaps are honored.
            self.session.setdefault("markers", []).append({"at": round(self.elapsed(), 2), "note": arg.strip()})
            self._save_session()
            log.info("%s: marker at %.1f s", self.rec.id, self.elapsed())
        elif word == "note":
            markers = self.session.get("markers") or []
            if markers:
                markers[-1]["note"] = arg.strip()
                self._save_session()
        else:
            log.warning("%s: unknown command %r", self.rec.id, word)

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

    @property
    def computer_audio(self) -> bool:
        return bool(self.session.get("computer_audio"))

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
            "out_take": self.out.path.name if self.out else None,
            "tracks": tracks.TRACKS if self.computer_audio else None,
            "rate": self.rate, "channels": self.channels, "warning": self.warning,
            "source": self.session.get("source_label"), "supervisor_pid": os.getpid(),
            "token": self.token, "updated": time.time(),
        })

    # ---- takes ----
    def _start_take(self) -> bool:
        n = len(take_files(self.rec)) + 1
        path = self.rec.takes_dir / f"take-{n:03d}.raw"
        while path.exists() or (self.rec.takes_dir / f"out-{n:03d}.raw").exists():
            n += 1
            path = self.rec.takes_dir / f"take-{n:03d}.raw"
        path.touch()
        before = recorded_bytes(self.rec)  # audio already captured, without this new take
        logf = open(path.with_suffix(".log"), "ab")
        try:
            self.capture = self.backend.start_capture(self.source, self.rate, self.channels, path, logf)
        except Exception as e:  # noqa: BLE001 - a device that cannot be opened now must not end the recording
            # (PortAudio raises its own errors, and ValueError when there is no input at all.)
            self.capture = None
            self.warning = f"Could not start capture: {e}"
            log.error(self.warning)
            return False
        finally:
            logf.close()
        actual = getattr(self.capture, "rate", None)
        if actual and actual != self.rate:
            if before == 0:
                # The device records only at its own rate (WASAPI shared mode); the session follows.
                log.info("%s: device rate %d Hz instead of %d", self.rec.id, actual, self.rate)
                self.session["rate"] = actual
            else:
                log.warning("%s: device now at %d Hz, recording at %d; this take is skipped",
                            self.rec.id, actual, self.rate)
                self.capture.stop()
                path.unlink(missing_ok=True)
                self.capture = None
                self.warning = "The input changed its sample rate; pick it again or restart the recording."
                return False
        entry = {"file": path.name, "pid": self.capture.pid, "started": _now_iso(),
                 "source": self.source.name if self.source else None, "ended": None, "end_reason": None}
        if self.computer_audio:
            self._start_out(n, entry)
        self.session.setdefault("takes", []).append(entry)
        self.take_file = path.name
        fsync_dir(self.rec.takes_dir)
        now = time.monotonic()
        self._take_started = now
        self._last_size = 0
        self._last_growth = now
        self._save_session()
        return True

    def _start_out(self, n: int, entry: dict[str, Any]) -> None:
        """The computer-audio half of a pair. If it cannot start, the input records on alone."""
        path = self.rec.takes_dir / f"out-{n:03d}.raw"
        path.touch()
        logf = open(path.with_suffix(".log"), "ab")
        try:
            self.out = self.backend.start_capture(backend.DEFAULT_OUTPUT, self.rate, self.channels, path, logf)
        except Exception as e:  # noqa: BLE001 - the input is the half that must not be lost
            self.out = None
            path.unlink(missing_ok=True)
            self.warning = f"Computer audio is not being recorded: {e}"
            self._warning_expires = 0.0
            if not self._out_warned:
                self._out_warned = True
                self._note(f"Could not record the computer audio: {e}")
            return
        finally:
            logf.close()
        entry["out"] = {"file": path.name, "pid": self.out.pid}
        self._out_last_size = 0
        self._out_last_growth = time.monotonic()

    def _end_take(self, reason: str):
        if not self.capture and not self.out:
            return
        # Both stopped by us while both ran: the pair ends on the same sample (see audio/tracks.py).
        together = (reason in ("paused", "stopped") and self.capture is not None and self.out is not None
                    and self.capture.alive() and self.out.alive())
        caps = [c for c in (self.capture, self.out) if c is not None]
        backend.stop_together(caps)
        takes = self.session.get("takes", [])
        entry = next((t for t in reversed(takes) if t["file"] == self.take_file), None)
        kept = False
        for c in caps:
            path = c.path
            fsync_path(path)
            if path.exists() and path.stat().st_size == 0:
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
                if entry is not None and c is self.out:
                    entry.pop("out", None)
            elif path.exists():
                kept = True
        if entry is not None:
            if kept:
                entry["ended"], entry["end_reason"] = _now_iso(), reason
                if together:
                    entry["align"] = "end"
            else:
                self.session["takes"] = [t for t in takes if t is not entry]
        self.capture = None
        self.out = None
        self.take_file = None
        self._save_session()

    def _restart(self, cause: str):
        produced = self.capture is not None and self.capture.path.exists() and self.capture.path.stat().st_size > 0
        if not produced:
            # Capture fails before any audio: back off instead of spinning, and say so once.
            self._fails += 1
            self._end_take("failed")
            delay = min(5.0, 0.5 * 2 ** (self._fails - 1))
            self._next_retry = time.monotonic() + delay
            if self._fails == FAILS_BEFORE_DEFAULT and self.source is not None and not backend.is_fake():
                fallback = self.backend.default_source()
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
        elif self.out is not None:
            self._check_out(now)

    def _check_out(self, now: float):
        """Either half of a pair failing restarts both, so the pairs stay aligned (audio/tracks.py)."""
        try:
            size = self.out.path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size != self._out_last_size:
            self._out_last_size = size
            self._out_last_growth = now
        if not self.out.alive():
            self._restart("Computer audio capture stopped unexpectedly; restarted")
        elif now - self._take_started > START_GRACE and now - self._out_last_growth > STALL_AFTER:
            self._restart("Computer audio capture stalled; restarted")

    def _check_source(self):
        if backend.is_fake() or self.source is None:
            return
        present = self.backend.find(self.source.name) is not None
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
        captured = recorded_bytes(self.rec) + recorded_bytes(self.rec, out_files(self.rec))
        reserve = int(captured * FLAC_RATIO) + DISK_MARGIN
        if free < reserve:
            self._note("Disk almost full; recording stopped")
            return False
        minutes_left = (free - reserve) / (self.bps * (2 if self.computer_audio else 1)) / 60
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
        self.session["token"] = self.token
        self.session.setdefault("started", _now_iso())
        wanted = self.session.get("source")
        self.source, note = self.backend.resolve(wanted or "")
        self.session["source_label"] = self.source.label if self.source else "System default input"
        if note:
            self.warning = note
            self.session["events"].append({"at": 0.0, "wall": _now_iso(), "cause": note, "kind": "info"})

    def _setup_adopt(self):
        self.session = load_session(self.rec) or {}
        if not self.session:
            raise RecorderError("no session to adopt")
        self.session["supervisor_pid"] = os.getpid()
        self.session["token"] = self.token
        name = None
        for t in self.session.get("takes", []):
            name = t.get("source") or name
        self.source = self.backend.find(name) if name else None
        last = (self.session.get("takes") or [None])[-1]
        if last and last.get("ended") is None:
            now = time.monotonic()
            self._take_started = now
            self.take_file = last["file"]
            path = self.rec.takes_dir / last["file"]
            capture = AdoptedCapture(last.get("pid"), path)
            if last.get("pid") is not None and capture.alive():
                self.capture = capture
                self._last_size = path.stat().st_size if path.exists() else 0
                self._last_growth = now
            out = last.get("out") or {}
            out_cap = AdoptedCapture(out.get("pid"), self.rec.takes_dir / out["file"]) if out.get("file") else None
            if out_cap is not None and out.get("pid") is not None and out_cap.alive():
                self.out = out_cap
                self._out_last_size = out_cap.path.stat().st_size if out_cap.path.exists() else 0
                self._out_last_growth = now
            if self.computer_audio and (self.capture is None) != (self.out is None):
                # One half of the pair died with the supervisor: a new pair brings both back.
                self._end_take("interrupted")
        self._note("Recorder restarted after a crash; capture continued", kind="info")

    def run(self) -> int:
        lock = locks.acquire(_lock_path(self.lib), wait=2.0)
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
            self._read_commands()
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
                    if self.out:
                        fsync_path(self.out.path)
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
        # Encoding and verifying hours of audio takes a while; the heartbeat goes on meanwhile so
        # nobody mistakes the supervisor for dead and starts recovering the same takes.
        import threading

        done = threading.Event()

        def beat():
            while not done.wait(STATUS_EVERY):
                if self.rec.takes_dir.is_dir():
                    self._status()

        def stop_beat():
            done.set()
            t.join()

        t = threading.Thread(target=beat, daemon=True)
        t.start()
        try:
            outcome = finalize(self.rec, before_cleanup=stop_beat)
        finally:
            stop_beat()
        return 0 if outcome in ("ready", "empty") else 1


# ---------------------------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------------------------

def finalize(rec: Recording, recovered: bool = False, before_cleanup=None) -> str:
    """Turn raw takes into verified FLAC. Returns 'ready', 'empty' or 'failed'.

    `before_cleanup` is called before the takes folder is removed (the supervisor stops its
    heartbeat there, so no status file is written into a folder being deleted).
    """
    def cleanup(path):
        if before_cleanup is not None:
            before_cleanup()
        shutil.rmtree(path, ignore_errors=True)

    session = load_session(rec) or {}
    rate = session.get("rate") or rec.meta.sample_rate or 48000
    channels = session.get("channels") or rec.meta.channels or 1
    takes = take_files(rec)
    two = bool(session.get("computer_audio")) or bool(out_files(rec))
    if two:
        # A call: the pairs become one file with the input on channel 1, the computer audio on 2.
        aligned = {t["file"] for t in session.get("takes", []) if t.get("align") == "end"}
        pairs = tracks.pairs(rec.takes_dir, aligned)
        total = sum(p.length() for p in pairs)
        channels = 2
    else:
        frame = 2 * channels
        total = sum(p.stat().st_size // frame * frame for p in takes)
    if total == 0:
        log.info("%s: no audio captured, removing", rec.id)
        cleanup(rec.folder)
        return "empty"
    if rec.meta.state == READY and rec.audio_path and rec.audio_path.exists():
        cleanup(rec.takes_dir)  # crashed after finalize, before cleanup
        return "ready"
    partial = rec.folder / "audio.flac.partial"
    final = rec.folder / "audio.flac"
    try:
        if two:
            frames = ffmpeg.encode_pcm_flac_verified(tracks.interleave(pairs), rate, channels, partial)
        else:
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
    new_markers = session.get("markers", [])
    if two:
        # Markers and notes were placed on the input alone; silence added to it moves them along.
        at = tracks.time_map(pairs, rate)
        events = [{**e, "at": at(e["at"])} for e in events]
        new_markers = [{**m, "at": at(m["at"])} for m in new_markers]
    markers = sorted({(m["at"], m.get("note", "")): m for m in [*rec.meta.markers, *new_markers]}
                     .values(), key=lambda m: m["at"])
    rec.update(state=READY, audio=final.name, sha256=ffmpeg.sha256_file(final), markers=markers,
               duration=round(frames / rate, 3), sample_rate=rate, channels=channels,
               recovered=recovered or rec.meta.recovered, gaps=events, error=None,
               tracks=tracks.TRACKS if two else None)
    cleanup(rec.takes_dir)
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

    def heartbeat_age(self) -> float | None:
        """Seconds since this session's supervisor last wrote its status; None if it never did."""
        st = read_status(self.rec)
        if not st:
            return None
        token = self.info().get("token")
        # A session without a token was started by the previous version, which wrote no token.
        if token is not None and st.get("token") != token:
            return None
        return max(0.0, time.time() - float(st.get("updated") or 0))

    @property
    def legacy(self) -> bool:
        """Started by the previous version: it understands signals, not command files."""
        return "token" not in self.info()

    def alive(self) -> bool:
        """The supervisor is answering: its heartbeat is fresh and carries this session's token."""
        age = self.heartbeat_age()
        return age is not None and age < HEARTBEAT_STALE and pid_alive(self.supervisor_pid)

    def hung(self) -> bool:
        """Its process exists but it stopped answering only moments ago; recovery waits."""
        age = self.heartbeat_age()
        return age is not None and HEARTBEAT_STALE <= age < HUNG_GRACE and pid_alive(self.supervisor_pid)

    def command(self, word: str) -> None:
        if not self.alive():
            raise RecorderError("The recorder for this recording is not running.")
        if self.legacy and os.name != "nt":
            sig = {"pause": "SIGUSR1", "resume": "SIGUSR2", "stop": "SIGTERM"}.get(word)
            if sig is None:
                raise RecorderError("This recording was started by an earlier version of Echo, which cannot "
                                    "add markers. Markers work in your next recording.")
            os.kill(self.supervisor_pid, getattr(signal, sig))
            return
        send_command(self.rec, word)

    def mark(self, note: str = "") -> None:
        """A marker at the current position of the captured audio."""
        self.command(f"mark {' '.join(note.split())}".rstrip())

    def note(self, text: str) -> None:
        """Attach a note to the latest marker."""
        self.command(f"note {' '.join(text.split())}")

    def markers(self) -> list[dict[str, Any]]:
        return list(self.info().get("markers") or [])

    def pause(self) -> None:
        self.command("pause")

    def resume(self) -> None:
        self.command("resume")

    def stop(self, wait: float = 0.0) -> str | None:
        """Ask the supervisor to stop. With wait > 0, block until finalized (returns outcome)."""
        self.command("stop")
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
          title: str | None = None, timeout: float = 5.0, quick_note: bool = False,
          computer_audio: bool = False) -> Session:
    """Start a detached supervisor for a new recording and wait until it is capturing.

    With `computer_audio`, the default output is recorded as a second track next to the input; each
    track is mono, whatever `channels` says.
    """
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
    if not backend.is_fake():
        src, _ = backend.get().resolve(source)
        label = src.label if src else "System default input"
        if computer_audio and src is not None and src.kind != backend.INPUT:
            raise RecorderError("The source is already the computer audio; choose a microphone to add it to.")
    if computer_audio:
        if not backend.get().records_outputs:
            raise RecorderError("This audio system cannot record the computer audio.")
        channels = 1
        label = f"{label or 'Default input'} + computer audio"
    now = datetime.now()
    rec = lib.create(title or f"Recording {now:%Y-%m-%d %H:%M}", "recorded", state=RECORDING,
                     source=label, sample_rate=rate, channels=channels, title_auto=not title,
                     quick_note=quick_note, tags=["nota"] if quick_note else [])
    rec.takes_dir.mkdir()
    atomic_write_json(session_path(rec), {"version": 1, "rate": rate, "channels": channels,
                                          "source": source or None, "state": S_STARTING,
                                          "computer_audio": computer_audio,
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
    return backend.detached_popen(selfcmd.command(*args), env=selfcmd.env(), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def _starting(rec: Recording) -> bool:
    """Created moments ago and its supervisor has not written a status yet: it is starting, not dead.

    The window or a second key press can run recovery while a recording starts; without this, its
    empty folder would look abandoned and be removed under the starting supervisor.
    """
    if rec.meta.state != RECORDING or read_status(rec):
        return False
    created = (load_session(rec) or {}).get("created") or rec.meta.created
    try:
        age = time.time() - datetime.fromisoformat(created).timestamp()
    except (TypeError, ValueError):
        return False
    return -5 <= age < STARTING_GRACE


def _capture_left(rec: Recording, take: dict[str, Any]) -> bool:
    """A capture of this take, the input's or the computer audio's, is still writing it."""
    out = take.get("out") or {}
    for pid, name in ((take.get("pid"), take.get("file")), (out.get("pid"), out.get("file"))):
        if pid is not None and name and AdoptedCapture(pid, rec.takes_dir / name).alive():
            return True
    return False


def recover_one(lib: Library, rec: Recording) -> str | None:
    if _starting(rec):
        return "live"
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
    if sess.alive() or sess.hung():
        return "live"
    if pid_alive(sess.supervisor_pid):
        lock = try_lock(lib)
        if lock is None:
            # Stuck for a while yet still holding the recording lock: it is our supervisor and it
            # may wake up. Recovering under it could finalize takes it is still writing.
            return "hung"
        lock.close()
    session = load_session(rec) or {}
    last = (session.get("takes") or [None])[-1]
    # Only a capture process can outlive its supervisor; an in-process stream (PortAudio) died with it.
    if last and last.get("ended") is None and _capture_left(rec, last):
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



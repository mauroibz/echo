"""The audio backend: listing sources, capturing takes, the idle meter, playback and listening.

Everything Echo does with audio devices goes through `get()`, so a second backend (PortAudio
for Windows, macOS and PulseAudio-only Linux) is one more implementation of `Backend`. The
PipeWire backend drives PipeWire's own command-line tools, as before; its guarantees (SIGINT
flushes `pw-record`, a SIGKILL loses at most its 4 KB buffer) are described in docs/design.md.

Capture, meter and output objects all look like small processes (`pid`, `alive`, `stop`), so
the recorder can treat a capture child and an in-process stream alike.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import BinaryIO, Protocol

from . import pipewire
from .pipewire import INPUT, MONITOR, Source

__all__ = ["Backend", "Capture", "BackendMissing", "INPUT", "MONITOR", "Source", "get"]


class BackendMissing(RuntimeError):
    pass


class Capture(Protocol):
    pid: int | None
    path: Path

    def alive(self) -> bool: ...
    def stop(self, timeout: float = 3.0) -> None: ...  # flush, then escalate


class Stream(Protocol):
    """Raw mono s16 for the level meter."""

    def read(self, n: int) -> bytes: ...  # b"" when the stream ended
    def running(self) -> bool: ...
    def stop(self) -> None: ...


class Output(Protocol):
    """Plays raw s16 read from a pipe until it ends."""

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class Backend(Protocol):
    name: str
    # Whether outputs can be recorded ("Computer audio") and inputs listened to.
    records_outputs: bool
    can_listen: bool

    def list_sources(self) -> list[Source]: ...
    def default_source(self, sources: list[Source] | None = None) -> Source | None: ...
    def find(self, name: str, sources: list[Source] | None = None) -> Source | None: ...
    def resolve(self, preferred: str, sources: list[Source] | None = None) -> tuple[Source | None, str | None]: ...
    def start_capture(self, source: Source | None, rate: int, channels: int, path: Path, log: BinaryIO) -> Capture: ...
    def meter(self, source: Source | None, rate: int) -> Stream: ...
    def output(self, rate: int, channels: int, stdin) -> Output: ...
    def listen(self, source: Source | None) -> Output | None: ...


# ---- processes ----------------------------------------------------------------------------------

class ProcessCapture:
    """A capture child that writes raw PCM to `path`."""

    def __init__(self, popen: subprocess.Popen, path: Path):
        self.popen = popen
        self.pid = popen.pid
        self.path = path

    def alive(self) -> bool:
        return self.popen.poll() is None

    def stop(self, timeout: float = 3.0) -> None:
        """SIGINT lets pw-record flush its buffer; escalate only if it hangs."""
        for sig, wait in ((signal.SIGINT, timeout), (signal.SIGKILL, 2.0)):
            if not self.alive():
                return
            try:
                self.popen.send_signal(sig)
            except (ProcessLookupError, OSError):
                return
            try:
                self.popen.wait(timeout=wait)
                return
            except subprocess.TimeoutExpired:
                continue


def detached_popen(cmd: list[str], **kw) -> subprocess.Popen:
    """A child in its own session or process group, so closing the window does not reach it."""
    if os.name == "nt":  # pragma: no cover
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        return subprocess.Popen(cmd, creationflags=flags, close_fds=True, **kw)
    return subprocess.Popen(cmd, start_new_session=True, close_fds=True, **kw)


class ProcessStream:
    def __init__(self, popen: subprocess.Popen):
        self.popen = popen

    def read(self, n: int) -> bytes:
        return self.popen.stdout.read(n) if self.popen.stdout else b""

    def running(self) -> bool:
        return self.popen.poll() is None

    def stop(self) -> None:
        if self.popen.poll() is None:
            self.popen.terminate()
            try:
                self.popen.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.popen.kill()


# ---- PipeWire -----------------------------------------------------------------------------------

class PipeWireBackend:
    name = "pipewire"
    records_outputs = True
    can_listen = True

    def list_sources(self) -> list[Source]:
        return pipewire.list_sources()

    def default_source(self, sources=None):
        return pipewire.default_source(self.list_sources() if sources is None else sources)

    def find(self, name, sources=None):
        return pipewire.find(name, self.list_sources() if sources is None else sources)

    def resolve(self, preferred, sources=None):
        return pipewire.resolve(preferred, self.list_sources() if sources is None else sources)

    def capture_cmd(self, source, rate, channels, path) -> list[str]:
        return pipewire.record_cmd(source, rate, channels, str(path))

    def start_capture(self, source, rate, channels, path, log) -> ProcessCapture:
        popen = detached_popen(self.capture_cmd(source, rate, channels, path), stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=log)
        return ProcessCapture(popen, Path(path))

    def meter(self, source, rate) -> ProcessStream:
        return ProcessStream(subprocess.Popen(pipewire.monitor_cmd(source, rate), stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL))

    def output(self, rate, channels, stdin) -> subprocess.Popen:
        return subprocess.Popen(
            ["pw-play", "--raw", "--rate", str(rate), "--channels", str(channels), "--format", "s16",
             "--latency", "50ms", "-P", '{ node.name="echo-player" node.description="Echo" application.name="Echo" }',
             "-"], stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def listen(self, source) -> subprocess.Popen:
        return subprocess.Popen(pipewire.loopback_cmd(source), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class CommandBackend(PipeWireBackend):
    """PipeWire with the capture command replaced (ECHO_CAPTURE_CMD, used by the tests).

    The template gets {path} and {bps}; sources are a single test input.
    """

    name = "command"

    def __init__(self, template: str):
        self.template = template

    def list_sources(self):
        return [Source("fake", "Test source", INPUT, 1, True)]

    def resolve(self, preferred, sources=None):
        return Source(preferred or "fake", "Test source", INPUT, 1, True), None

    def find(self, name, sources=None):
        return Source(name, "Test source", INPUT, 1, True)

    def capture_cmd(self, source, rate, channels, path):
        bps = rate * channels * 2
        return [part.format(path=str(path), bps=bps) for part in shlex.split(self.template)]


_backend: Backend | None = None


def get() -> Backend:
    """The backend for this machine. Raises BackendMissing with the doctor's advice."""
    global _backend
    if template := os.environ.get("ECHO_CAPTURE_CMD"):
        return CommandBackend(template)
    if _backend is None:
        if shutil.which("pw-record"):
            _backend = PipeWireBackend()
        else:
            raise BackendMissing("PipeWire's pw-record was not found. Run `echo-app doctor` for the fix.")
    return _backend


def is_fake() -> bool:
    return bool(os.environ.get("ECHO_CAPTURE_CMD"))

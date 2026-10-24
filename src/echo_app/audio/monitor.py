"""Live input level while idle, and listening to the input through the speakers."""

from __future__ import annotations

import logging
import subprocess
import threading

from . import levels, pipewire

log = logging.getLogger(__name__)

RATE = 16000
CHUNK = RATE // 20 * 2  # 50 ms of mono s16


class LevelMonitor:
    """Reads a low-rate mono stream of a source and keeps the latest peak level."""

    def __init__(self, source: pipewire.Source | None):
        self.source = source
        self.level = levels.SILENCE_DB
        self.clipped = False
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.stop()
        try:
            self._proc = subprocess.Popen(pipewire.monitor_cmd(self.source, RATE), stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except OSError as e:
            log.warning("level monitor failed to start: %s", e)
            return
        self._thread = threading.Thread(target=self._run, args=(self._proc,), daemon=True)
        self._thread.start()

    def _run(self, proc: subprocess.Popen) -> None:
        while True:
            data = proc.stdout.read(CHUNK)
            if not data:
                break
            self.level, clip = levels.peak(data)
            self.clipped = self.clipped or clip
        self.level = levels.SILENCE_DB

    def take_clip(self) -> bool:
        clip, self.clipped = self.clipped, False
        return clip

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        self.level = levels.SILENCE_DB


class Listener:
    """Plays the selected input through the default output (pw-loopback)."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, source: pipewire.Source | None) -> None:
        self.stop()
        try:
            self._proc = subprocess.Popen(pipewire.loopback_cmd(source), stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            log.warning("listening failed to start: %s", e)
            self._proc = None

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

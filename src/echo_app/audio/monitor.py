"""Live input level while idle, and listening to the input through the speakers."""

from __future__ import annotations

import logging
import threading

from . import backend, levels
from .backend import Source

log = logging.getLogger(__name__)

RATE = 16000
CHUNK = RATE // 20 * 2  # 50 ms of mono s16


class LevelMonitor:
    """Reads a low-rate mono stream of a source and keeps the latest peak level."""

    def __init__(self, source: Source | None):
        self.source = source
        self.level = levels.SILENCE_DB
        self.clipped = False
        self._proc: backend.Stream | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.stop()
        try:
            self._proc = backend.get().meter(self.source, RATE)
        except (OSError, backend.BackendMissing) as e:
            log.warning("level monitor failed to start: %s", e)
            return
        self._thread = threading.Thread(target=self._run, args=(self._proc,), daemon=True)
        self._thread.start()

    def _run(self, proc: backend.Stream) -> None:
        while True:
            data = proc.read(CHUNK)
            if not data:
                break
            self.level, clip = levels.peak(data)
            self.clipped = self.clipped or clip
        self.level = levels.SILENCE_DB

    def take_clip(self) -> bool:
        clip, self.clipped = self.clipped, False
        return clip

    def running(self) -> bool:
        return self._proc is not None and self._proc.running()

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.stop()
            self._proc = None
        self.level = levels.SILENCE_DB


class Listener:
    """Plays the selected input through the default output, where the backend can."""

    def __init__(self):
        self._proc: backend.Output | None = None

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, source: Source | None) -> None:
        self.stop()
        try:
            self._proc = backend.get().listen(source)
        except (OSError, backend.BackendMissing) as e:
            log.warning("listening failed to start: %s", e)
            self._proc = None

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except Exception:  # noqa: BLE001 - a process or a stream; either way it is gone
                pass
            self._proc = None

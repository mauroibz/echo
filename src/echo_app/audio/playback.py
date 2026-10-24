"""Playback through ffmpeg (decode from any position, any format) piped into pw-play.

No media framework needed: seeking or changing speed restarts the pipeline at the new position,
which takes about a tenth of a second.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)

RATE = 48000
CHANNELS = 2
OUTPUT_LATENCY = 0.06  # seconds between writing and hearing (pw-play --latency 50ms + buffering)


def _atempo(speed: float) -> list[str]:
    if abs(speed - 1.0) < 1e-3:
        return []
    return ["-af", f"atempo={speed:.3f}"]


class Playback:
    def __init__(self):
        self.path: Path | None = None
        self.duration = 0.0
        self.speed = 1.0
        self._pos = 0.0  # position when stopped, or start position of the running pipeline
        self._t0 = 0.0
        self._end: float | None = None
        self._dec: subprocess.Popen | None = None
        self._out: subprocess.Popen | None = None
        self.error: str | None = None

    # ---- state ----
    def load(self, path: Path | None, duration: float) -> None:
        self.stop()
        self.path = Path(path) if path else None
        self.duration = max(0.0, duration or 0.0)
        self._pos = 0.0
        self.error = None

    @property
    def playing(self) -> bool:
        return self._out is not None

    def position(self) -> float:
        if not self.playing:
            return self._pos
        elapsed = max(0.0, time.monotonic() - self._t0 - OUTPUT_LATENCY) * self.speed
        pos = self._pos + elapsed
        limit = self._end if self._end is not None else self.duration
        return min(pos, limit) if limit else pos

    def poll(self) -> bool:
        """Call periodically. Returns True if playback just reached its end."""
        if not self.playing:
            return False
        if self._out.poll() is not None:
            end = self.position()
            err = None
            if self._dec is not None and self._dec.poll() not in (0, None):
                err = (self._dec.stderr.read() or b"").decode(errors="replace").strip()[-300:] if self._dec.stderr else ""
            self._cleanup()
            if err:
                self.error = err or "playback failed"
                log.warning("playback error: %s", self.error)
            self._pos = end
            return True
        return False

    # ---- control ----
    def play(self, start: float | None = None, end: float | None = None) -> None:
        if self.path is None:
            return
        self.stop()
        pos = self._pos if start is None else start
        if self.duration and pos >= self.duration - 0.05:
            pos = 0.0
        self._pos = max(0.0, pos)
        self._end = end
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{self._pos:.3f}"]
        if end is not None:
            cmd += ["-t", f"{max(0.05, end - self._pos):.3f}"]
        cmd += ["-i", str(self.path), "-vn", *_atempo(self.speed), "-f", "s16le", "-ac", str(CHANNELS),
                "-ar", str(RATE), "pipe:1"]
        try:
            self._dec = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
            self._out = subprocess.Popen(
                ["pw-play", "--raw", "--rate", str(RATE), "--channels", str(CHANNELS), "--format", "s16",
                 "--latency", "50ms", "-P", '{ node.name="echo-player" node.description="Echo" application.name="Echo" }',
                 "-"], stdin=self._dec.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._dec.stdout.close()  # pw-play owns the read end now
        except OSError as e:
            self.error = f"cannot start playback: {e}"
            self._cleanup()
            return
        self._t0 = time.monotonic()
        self.error = None

    def pause(self) -> None:
        if self.playing:
            self._pos = self.position()
            self._cleanup()

    def stop(self) -> None:
        self.pause()

    def seek(self, sec: float) -> None:
        sec = max(0.0, min(sec, self.duration or sec))
        if self.playing:
            self.play(sec, self._end)
        else:
            self._pos = sec

    def set_speed(self, speed: float) -> None:
        if abs(speed - self.speed) < 1e-3:
            return
        was = self.playing
        pos = self.position()
        self.pause()
        self.speed = speed
        self._pos = pos
        if was:
            self.play(pos, self._end)

    def _cleanup(self) -> None:
        for p in (self._out, self._dec):
            if p is not None and p.poll() is None:
                p.terminate()
        for p in (self._out, self._dec):
            if p is not None:
                try:
                    p.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    p.kill()
        if self._dec is not None and self._dec.stderr:
            self._dec.stderr.close()
        self._out = self._dec = None

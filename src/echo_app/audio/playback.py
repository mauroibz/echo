"""Playback through ffmpeg (decode from any position, any format) piped into the backend's output
(pw-play with PipeWire).

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
        from . import backend

        try:
            self._dec = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
            self._out = backend.get().output(RATE, CHANNELS, self._dec.stdout)
            if isinstance(self._out, subprocess.Popen):
                self._dec.stdout.close()  # the output process owns the read end now
        except (OSError, backend.BackendMissing) as e:
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


class SetPlayback:
    """A linked set's parts played back to back, on the set's timeline.

    Positions are set time: the parts' cropped spans laid end to end (see sets.timeline). One
    part plays at a time through a Playback; when it reaches the end of its span the next part
    starts, which takes the same tenth of a second as a seek.
    """

    def __init__(self):
        self.inner = Playback()
        self.parts: list = []  # sets.Part
        self.k = 0
        self._end: float | None = None  # set time where a span stops
        self.error: str | None = None

    @property
    def duration(self) -> float:
        return sum(p.length for p in self.parts)

    @property
    def speed(self) -> float:
        return self.inner.speed

    @property
    def path(self):
        return self.inner.path

    @property
    def playing(self) -> bool:
        return self.inner.playing

    def load(self, parts: list) -> None:
        self.stop()
        self.parts = list(parts)  # all of them: the offsets are the waveform's and the text's
        self.k = -1
        self._end = None
        self.error = None
        self._use(0)

    def _use(self, k: int) -> None:
        if not self.parts:
            self.inner.load(None, 0)
            return
        k = max(0, min(k, len(self.parts) - 1))
        if k != self.k:
            p = self.parts[k]
            self.inner.load(p.rec.audio_path if self._playable(k) else None, p.rec.meta.duration or 0)
            self.inner.seek(p.start)
            self.k = k

    def _part_at(self, t: float) -> int:
        for i, p in enumerate(self.parts):
            if t < p.offset + p.length - 0.02:
                return i
        return len(self.parts) - 1

    def position(self) -> float:
        if not self.parts:
            return 0.0
        p = self.parts[self.k]
        return p.offset + max(0.0, self.inner.position() - p.start)

    def _playable(self, k: int) -> bool:
        path = self.parts[k].rec.audio_path
        return path is not None and path.exists() and self.parts[k].length > 0

    def _play_part(self, start: float) -> None:
        while not self._playable(self.k):  # a part without audio is passed over
            if self.k + 1 >= len(self.parts):
                return
            self._use(self.k + 1)
            start = self.parts[self.k].offset
        p = self.parts[self.k]
        stop = p.start + p.length
        if self._end is not None:
            stop = min(stop, p.to_part(self._end))
        self.inner.play(p.to_part(start), stop)
        self.error = self.inner.error

    def play(self, start: float | None = None, end: float | None = None) -> None:
        if not self.parts:
            return
        pos = self.position() if start is None else start
        if pos >= self.duration - 0.05:
            pos = 0.0
        self._end = end
        self._use(self._part_at(pos))
        self._play_part(max(pos, self.parts[self.k].offset))

    def poll(self) -> bool:
        """Call periodically. True when playback reached its end (the set's, or a span's)."""
        if not self.inner.poll():
            return False
        if self.inner.error:
            self.error = self.inner.error
            return True
        if self._end is not None and self.position() >= self._end - 0.05:
            return True
        if self.k + 1 < len(self.parts):
            self._use(self.k + 1)
            self._play_part(self.parts[self.k].offset)
            return not self.playing  # nothing left with audio: the end
        return True

    def pause(self) -> None:
        self.inner.pause()

    def stop(self) -> None:
        self.inner.stop()

    def seek(self, sec: float) -> None:
        if not self.parts:
            return
        sec = max(0.0, min(sec, self.duration))
        if self.playing:
            self.play(sec, self._end)
            return
        self._use(self._part_at(sec))
        self.inner.seek(self.parts[self.k].to_part(sec))

    def set_speed(self, speed: float) -> None:
        self.inner.set_speed(speed)

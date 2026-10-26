"""Two-track recordings: aligning pairs of takes and interleaving them into two channels (stdlib only).

A call recording captures the input and the computer audio in two processes, as pairs of raw mono
takes (``take-NNN.raw`` and ``out-NNN.raw``). Both run on PipeWire's one graph clock, so within a
pair the only difference is when each capture started (measured: up to 0.3 s when a device wakes
from suspend). A pair the supervisor stopped together ends on the same sample and is aligned at
its end; any other pair is aligned at its start. The shorter take of a pair gets silence, never
the longer one trimmed: no captured sample is dropped. When that silence goes on the input, times
measured on the input alone (markers, gap notes) move with it, through `time_map`.
"""

from __future__ import annotations

import re
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

MIC, COMPUTER = "mic", "computer"
TRACKS = [MIC, COMPUTER]
SAMPLE = 2  # bytes of one mono s16 sample
CHUNK = 1 << 18  # frames per interleaved chunk (1 MB out)

_NUM = re.compile(r"^(?:take|out)-(\d+)\.raw$")


@dataclass
class Pair:
    mic: Path | None
    out: Path | None
    align_end: bool = False

    @staticmethod
    def frames(path: Path | None) -> int:
        try:
            return path.stat().st_size // SAMPLE if path is not None else 0
        except FileNotFoundError:
            return 0

    def pads(self) -> tuple[int, int, int, int]:
        """Silence (input before, input after, output before, output after) that evens the pair."""
        m, o = self.frames(self.mic), self.frames(self.out)
        n = max(m, o)
        if self.align_end:
            return n - m, 0, n - o, 0
        return 0, n - m, 0, n - o

    def length(self) -> int:
        return max(self.frames(self.mic), self.frames(self.out))


def pairs(takes_dir: Path, aligned_end: set[str] = frozenset()) -> list[Pair]:
    """Every pair in the folder, by take number; `aligned_end` names input takes stopped together."""
    nums: set[int] = set()
    for p in takes_dir.iterdir():
        if m := _NUM.match(p.name):
            nums.add(int(m.group(1)))
    out = []
    for n in sorted(nums):
        mic, comp = takes_dir / f"take-{n:03d}.raw", takes_dir / f"out-{n:03d}.raw"
        out.append(Pair(mic if mic.exists() else None, comp if comp.exists() else None, mic.name in aligned_end))
    return out


class _Track:
    """One side of a pair as samples: silence before, the take, then silence for whatever is asked."""

    def __init__(self, path: Path | None, before: int):
        self.frames = Pair.frames(path)
        self.f = open(path, "rb") if self.frames else None
        self.before = before

    def read(self, n: int) -> array:
        out = array("h", bytes(SAMPLE * min(n, self.before)))
        self.before -= len(out)
        n -= len(out)
        if n and self.frames:
            k = min(n, self.frames)
            data = self.f.read(SAMPLE * k)
            out.frombytes(data + bytes(SAMPLE * k - len(data)))
            self.frames -= k
            n -= k
        if n:
            out.frombytes(bytes(SAMPLE * n))
        return out

    def close(self) -> None:
        if self.f:
            self.f.close()


def interleave(ps: list[Pair]) -> Iterator[bytes]:
    """The pairs as interleaved two-channel s16 PCM: the input on channel 1, the computer audio on 2.

    Only sample order changes, never byte order within a sample, so this holds on any machine.
    """
    for p in ps:
        mb, _, ob, _ = p.pads()
        mic, comp = _Track(p.mic, mb), _Track(p.out, ob)
        try:
            remaining = p.length()
            while remaining:
                k = min(CHUNK, remaining)
                buf = array("h", bytes(2 * SAMPLE * k))
                buf[0::2] = mic.read(k)
                buf[1::2] = comp.read(k)
                remaining -= k
                yield buf.tobytes()
        finally:
            mic.close()
            comp.close()


def time_map(ps: list[Pair], rate: int) -> Callable[[float], float]:
    """Seconds of input audio alone (as the supervisor counts them) to seconds of the finished file."""
    points = []  # (input frame where a pair's take begins, file frame where it lands)
    mic_pos = file_pos = 0
    for p in ps:
        mb, _, _, _ = p.pads()
        points.append((mic_pos, file_pos + mb))
        mic_pos += Pair.frames(p.mic)
        file_pos += p.length()

    def f(t: float) -> float:
        frame = t * rate
        start, at = 0, 0
        for s, a in points:
            if s > frame:
                break
            start, at = s, a
        return round((frame - start + at) / rate, 2)

    return f

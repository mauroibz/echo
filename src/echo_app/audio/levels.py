"""Level metering on raw s16le PCM (stdlib only)."""

from __future__ import annotations

import math
import os
import sys
from array import array

SILENCE_DB = -90.0
CLIP_THRESHOLD = 32700


def peak(pcm: bytes) -> tuple[float, bool]:
    """Return (peak level in dBFS, clipped) for s16le mono or interleaved PCM."""
    n = len(pcm) // 2
    if n == 0:
        return SILENCE_DB, False
    a = array("h")
    a.frombytes(pcm[: n * 2])
    if sys.byteorder == "big":
        a.byteswap()
    p = max(max(a), -min(a))
    db = 20 * math.log10(p / 32768) if p else SILENCE_DB
    return max(db, SILENCE_DB), p >= CLIP_THRESHOLD


def tail_peak(path, rate: int, channels: int, window_s: float = 0.05) -> tuple[float, bool]:
    """Peak of the last `window_s` seconds of a growing raw file."""
    frame = 2 * channels
    want = int(rate * window_s) * frame
    try:
        with open(path, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            size -= size % frame
            start = max(0, size - want)
            f.seek(start)
            return peak(f.read(size - start))
    except OSError:
        return SILENCE_DB, False

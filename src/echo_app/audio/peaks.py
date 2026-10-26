"""Waveform peaks: min/max per 10 ms, computed with ffmpeg and cached by content hash."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np


from . import ffmpeg

RATE = 8000
BUCKET = 80  # samples per bucket = 10 ms at 8 kHz
BUCKETS_PER_SECOND = RATE // BUCKET


def cache_dir() -> Path:
    from .. import paths

    base = paths.cache_dir() / "peaks"
    base.mkdir(parents=True, exist_ok=True)
    return base


def compute(path: Path, cache_key: str | None = None, mix: bool = False) -> np.ndarray:
    """Return an (N, 2) int16 array of [min, max] per 10 ms bucket; `mix` for a call's two tracks."""
    cached = cache_dir() / f"{cache_key}.npy" if cache_key else None
    if cached and cached.exists():
        try:
            return np.load(cached)
        except (OSError, ValueError):
            cached.unlink(missing_ok=True)
    proc = subprocess.Popen(ffmpeg.decode_cmd(path, RATE, mix=mix), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks = []
    leftover = b""
    block = BUCKET * 2 * 4096
    while True:
        data = proc.stdout.read(block)
        if not data:
            break
        data = leftover + data
        usable = len(data) // (BUCKET * 2) * (BUCKET * 2)
        leftover = data[usable:]
        a = np.frombuffer(data[:usable], dtype=np.int16).reshape(-1, BUCKET)
        chunks.append(np.stack([a.min(axis=1), a.max(axis=1)], axis=1))
    proc.wait()
    if leftover and len(leftover) >= 2:
        a = np.frombuffer(leftover[: len(leftover) // 2 * 2], dtype=np.int16)
        chunks.append(np.array([[a.min(), a.max()]], dtype=np.int16))
    peaks = np.concatenate(chunks) if chunks else np.zeros((0, 2), dtype=np.int16)
    if cached is not None and len(peaks):
        tmp = cached.with_suffix(".tmp.npy")
        np.save(tmp, peaks)
        os.replace(tmp, cached)
    return peaks


def snap(peaks: np.ndarray, t: float, radius: float = 0.3) -> float:
    """Move t to the quietest 10 ms bucket within ±radius seconds."""
    if not len(peaks):
        return t
    i = int(t * BUCKETS_PER_SECOND)
    r = int(radius * BUCKETS_PER_SECOND)
    lo, hi = max(0, i - r), min(len(peaks), i + r + 1)
    if hi <= lo:
        return t
    amp = np.abs(peaks[lo:hi].astype(np.int32)).max(axis=1)
    # Prefer the quietest point; among equals, the one closest to t.
    quiet = amp.min()
    candidates = np.flatnonzero(amp <= quiet + 30)
    best = candidates[np.argmin(np.abs(candidates + lo - i))]
    return (lo + int(best)) / BUCKETS_PER_SECOND


def playback_cache(sha: str) -> Path:
    from .. import paths

    d = paths.cache_dir() / "playback"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sha}.flac"



"""ffmpeg/ffprobe helpers (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

CHUNK = 1 << 20


class FFmpegError(RuntimeError):
    pass


@dataclass
class Probe:
    duration: float | None
    codec: str | None
    sample_rate: int | None
    channels: int | None
    format_name: str | None


def probe(path: Path) -> Probe:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         "-select_streams", "a", str(path)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        msg = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "ffprobe failed"
        raise FFmpegError(msg.replace(f"{path}: ", "").strip())
    d = json.loads(r.stdout or "{}")
    streams = d.get("streams") or []
    if not streams:
        raise FFmpegError("no audio stream found")
    st = streams[0]
    fmt = d.get("format") or {}
    dur = st.get("duration") or fmt.get("duration")
    return Probe(
        duration=float(dur) if dur not in (None, "N/A") else None,
        codec=st.get("codec_name"),
        sample_rate=int(st["sample_rate"]) if st.get("sample_rate") else None,
        channels=st.get("channels"),
        format_name=fmt.get("format_name"),
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def encode_flac_verified(takes: list[Path], rate: int, channels: int, out: Path) -> int:
    """Concatenate raw s16le takes into FLAC at `out`, verifying a bit-exact round trip.

    Returns the number of frames. Raises FFmpegError (and removes `out`) on any mismatch.
    """
    frame = 2 * channels
    fmt = ["-f", "s16le", "-ar", str(rate), "-ac", str(channels)]
    enc = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *fmt, "-i", "pipe:0",
         "-c:a", "flac", "-compression_level", "5", "-f", "flac", str(out)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    h_in = hashlib.sha256()
    total = 0
    try:
        for take in takes:
            usable = os.path.getsize(take)
            usable -= usable % frame
            with open(take, "rb") as f:
                remaining = usable
                while remaining:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    h_in.update(chunk)
                    total += len(chunk)
                    enc.stdin.write(chunk)
        enc.stdin.close()
        err = enc.stderr.read().decode(errors="replace")
        if enc.wait() != 0:
            raise FFmpegError(f"FLAC encode failed: {err.strip()}")
        dec = subprocess.Popen(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(out),
             "-f", "s16le", "-ac", str(channels), "-ar", str(rate), "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        h_out = hashlib.sha256()
        got = 0
        while chunk := dec.stdout.read(CHUNK):
            h_out.update(chunk)
            got += len(chunk)
        err = dec.stderr.read().decode(errors="replace")
        if dec.wait() != 0:
            raise FFmpegError(f"FLAC verify decode failed: {err.strip()}")
        if got != total or h_out.digest() != h_in.digest():
            raise FFmpegError(f"FLAC verification mismatch ({got} vs {total} bytes)")
    except BaseException:
        try:
            enc.kill()
        except OSError:
            pass
        Path(out).unlink(missing_ok=True)
        raise
    return total // frame


def decode_cmd(path: Path, rate: int, channels: int = 1, start: float | None = None,
               end: float | None = None) -> list[str]:
    """Command that decodes any audio file to raw s16le on stdout."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if end is not None:
        cmd += ["-t", f"{max(0.0, end - (start or 0.0)):.3f}"]
    return cmd + ["-vn", "-f", "s16le", "-ac", str(channels), "-ar", str(rate), "pipe:1"]

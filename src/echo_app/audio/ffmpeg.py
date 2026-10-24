"""ffmpeg/ffprobe helpers (stdlib only)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

CHUNK = 1 << 20


class FFmpegError(RuntimeError):
    pass


@dataclass
class Track:
    index: int  # stream index in the file, for -map 0:<index>
    codec: str | None
    duration: float | None
    sample_rate: int | None
    channels: int | None
    default: bool


@dataclass
class Probe:
    duration: float | None
    codec: str | None
    sample_rate: int | None
    channels: int | None
    format_name: str | None
    has_video: bool = False  # a real picture stream, not cover art
    tracks: list[Track] = field(default_factory=list)
    track: Track | None = None  # the audio track Echo uses: the default one, else the first


class NoAudio(FFmpegError):
    def __init__(self, has_video: bool):
        super().__init__("this video has no sound" if has_video else "no audio stream found")
        self.has_video = has_video


def _num(v) -> float | None:
    return float(v) if v not in (None, "N/A") else None


def probe(path: Path) -> Probe:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        msg = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "ffprobe failed"
        raise FFmpegError(msg.replace(f"{path}: ", "").strip())
    d = json.loads(r.stdout or "{}")
    streams = d.get("streams") or []
    fmt = d.get("format") or {}
    # Cover art in .m4a, .mp3 and .flac files is a video stream marked as an attached picture.
    has_video = any(st.get("codec_type") == "video" and not (st.get("disposition") or {}).get("attached_pic")
                    for st in streams)
    tracks = [Track(index=int(st.get("index", i)), codec=st.get("codec_name"),
                    duration=_num(st.get("duration")) or _num(fmt.get("duration")),
                    sample_rate=int(st["sample_rate"]) if st.get("sample_rate") else None,
                    channels=st.get("channels"),
                    default=bool((st.get("disposition") or {}).get("default")))
              for i, st in enumerate(streams) if st.get("codec_type") == "audio"]
    if not tracks:
        raise NoAudio(has_video)
    track = next((t for t in tracks if t.default), tracks[0])
    return Probe(duration=track.duration, codec=track.codec, sample_rate=track.sample_rate,
                 channels=track.channels, format_name=fmt.get("format_name"), has_video=has_video,
                 tracks=tracks, track=track)


# ---- audio out of a video ----------------------------------------------------------------------

# Codecs that go into an audio file unchanged: codec -> (extension, muxer, extra output options).
COPY_AS = {
    "aac": (".m4a", "ipod", ["-movflags", "+faststart"]),
    "opus": (".opus", "opus", []),
    "mp3": (".mp3", "mp3", []),
    "vorbis": (".ogg", "ogg", []),
    "flac": (".flac", "flac", []),
}
COPY = "copy"
ENCODE = "encode"


def extraction_plan(track: Track) -> tuple[str, str, list[str]]:
    """(extension, method, ffmpeg output options) for storing `track` as an audio file.

    A lossy track is copied when an audio container takes it: re-encoding could only lose
    quality. PCM stays lossless as FLAC, like Echo's own recordings. Anything else becomes Opus
    at 128 kb/s, transparent for speech; more than two channels are mixed down to stereo, since
    libopus refuses some surround layouts and speech gains nothing from them.
    """
    codec = track.codec or ""
    if codec in COPY_AS:
        ext, muxer, extra = COPY_AS[codec]
        return ext, COPY, ["-c:a", "copy", *extra, "-f", muxer]
    if codec.startswith("pcm_"):
        return ".flac", ENCODE, ["-c:a", "flac", "-compression_level", "5", "-f", "flac"]
    down = ["-ac", "2"] if (track.channels or 2) > 2 else []
    return ".opus", ENCODE, ["-c:a", "libopus", "-b:a", "128k", *down, "-f", "opus"]


def extract_audio(src: Path, track: Track, dest: Path, method_opts: list[str],
                  progress: Callable[[float], None] | None = None) -> None:
    """Write one audio track of `src` to `dest` with the options from extraction_plan()."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-map", f"0:{track.index}", "-vn", "-sn", "-dn", "-map_metadata", "-1",
           *method_opts, "-progress", "pipe:1", "-nostats", str(dest)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if progress and key == "out_time_us" and track.duration and value.isdigit():
                progress(min(1.0, int(value) / 1e6 / track.duration))
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise FFmpegError(err.strip().splitlines()[-1] if err.strip() else "ffmpeg failed")
    except BaseException:
        proc.kill()
        proc.wait()
        raise


def _hash(cmd: list[str]) -> str:
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *cmd],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise FFmpegError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "ffmpeg failed")
    return r.stdout.strip().rsplit("=", 1)[-1]


def packet_hash(path: Path, index: int) -> str:
    return _hash(["-i", str(path), "-map", f"0:{index}", "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"])


def sound_hash(path: Path, index: int) -> str:
    """Hash of the decoded samples: the same sound whatever container holds the packets."""
    return _hash(["-i", str(path), "-map", f"0:{index}", "-f", "hash", "-hash", "sha256", "-"])


def decoded_seconds(path: Path) -> float:
    out = subprocess.run(decode_cmd(path, 8000), capture_output=True, timeout=3600).stdout
    return len(out) / 2 / 8000


def verify_extraction(src: Path, track: Track, dest: Path, method: str) -> None:
    """Raise FFmpegError unless `dest` holds the sound of `src`'s track.

    A copy must carry the same packets; when the container reframes them (ADTS AAC from an
    MPEG-TS file loses its headers in .m4a) the decoded samples must be identical instead.
    An encode must decode to the same length within half a second.
    """
    if method == COPY:
        if packet_hash(src, track.index) == packet_hash(dest, 0):
            return
        if sound_hash(src, track.index) == sound_hash(dest, 0):
            return
        raise FFmpegError("verification failed")
    got = decoded_seconds(dest)
    want = track.duration or decoded_seconds(src)
    if abs(got - want) > 0.5:
        raise FFmpegError(f"verification failed ({got:.1f} s of {want:.1f} s)")


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

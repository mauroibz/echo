"""Import external audio files into the library, unchanged and verified (stdlib only)."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from . import features
from .audio import ffmpeg
from .fsutil import fsync_dir
from .library import READY, Library, Recording

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".opus", ".ogg", ".oga", ".m4a", ".mp4", ".aac", ".mp3", ".wav", ".wave", ".flac", ".amr",
    ".3gp", ".3ga", ".webm", ".weba", ".wma", ".aiff", ".aif", ".aifc", ".caf", ".mka", ".m4b",
    ".awb", ".spx",
}
STAGING = ".import"
CHUNK = 1 << 20

IMPORTED = "imported"
DUPLICATE = "duplicate"
REJECTED = "rejected"


@dataclass
class Result:
    source: Path
    status: str  # IMPORTED | DUPLICATE | REJECTED
    message: str
    recording: Recording | None = None


# ---- names and dates ---------------------------------------------------------------------------

_WA_ANDROID = re.compile(r"^(?P<kind>PTT|AUD)-(?P<d>\d{8})-WA\d+", re.I)
_WA_DESKTOP = re.compile(
    r"^WhatsApp (?P<kind>Audio|Ptt|Voice Note)\s+(?P<d>\d{4}-\d{2}-\d{2})\s+(?:at|a las)\s+"
    r"(?P<h>\d{1,2})[.:](?P<m>\d{2})[.:](?P<s>\d{2})"
    r"(?:\s*(?P<ampm>[ap])\.?\s?m\.?)?", re.I)


def title_and_date(path: Path) -> tuple[str, datetime]:
    """Derive a readable title and the best known recording date from a file name."""
    stem = path.stem
    m = _WA_DESKTOP.match(stem)
    if m:
        hour = int(m["h"])
        if m["ampm"]:
            hour = hour % 12 + (12 if m["ampm"].lower() == "p" else 0)
        dt = datetime.strptime(f"{m['d']} {hour:02d}:{m['m']}:{m['s']}", "%Y-%m-%d %H:%M:%S")
        return f"WhatsApp voice note {dt:%Y-%m-%d %H:%M}", dt
    m = _WA_ANDROID.match(stem)
    if m:
        dt = datetime.strptime(m["d"], "%Y%m%d")
        mtime = _mtime(path)
        if mtime and mtime.date() == dt.date():
            dt = mtime  # same day: the file time adds the time of day
            title = f"WhatsApp voice note {dt:%Y-%m-%d %H:%M}"
        else:
            title = f"WhatsApp voice note {dt:%Y-%m-%d}"
        if m["kind"].upper() == "AUD":
            title = title.replace("voice note", "audio")
        return title, dt
    title = re.sub(r"[_]+", " ", stem).strip() or path.name
    return title, _mtime(path) or datetime.now()


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


# ---- discovery ----------------------------------------------------------------------------------

def expand(paths: Iterable[Path]) -> list[Path]:
    """Files as given; folders searched recursively for audio extensions. Order is stable."""
    out: list[Path] = []
    seen: set[Path] = set()
    for p in paths:
        p = Path(p)
        if p.is_dir():
            found = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
                           and not any(part.startswith(".") for part in f.relative_to(p).parts))
        else:
            found = [p]
        for f in found:
            r = f.resolve()
            if r not in seen:
                seen.add(r)
                out.append(f)
    return out


def library_hashes(lib: Library) -> dict[str, Recording]:
    hashes = {}
    for rec in lib.all():
        if rec.meta.sha256:
            hashes[rec.meta.sha256] = rec
    return hashes


def clean_staging(lib: Library) -> None:
    shutil.rmtree(lib.data_dir / STAGING, ignore_errors=True)


# ---- import ------------------------------------------------------------------------------------

def _copy_verified(src: Path, dest: Path) -> str:
    """Copy src to dest computing sha256, fsync, then re-read dest to verify. Returns the hash."""
    h = hashlib.sha256()
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        while chunk := fi.read(CHUNK):
            h.update(chunk)
            fo.write(chunk)
        fo.flush()
        os.fsync(fo.fileno())
    digest = h.hexdigest()
    if ffmpeg.sha256_file(dest) != digest:
        raise OSError("copy verification failed")
    return digest


def _duration(path: Path, probed: float | None) -> float | None:
    if probed:
        return probed
    try:
        out = subprocess.run(ffmpeg.decode_cmd(path, 8000), capture_output=True, timeout=600).stdout
        return round(len(out) / 2 / 8000, 3) if out else None
    except (OSError, subprocess.SubprocessError):
        return None


def import_file(lib: Library, src: Path, hashes: dict[str, Recording] | None = None) -> Result:
    src = Path(src)
    if not src.is_file():
        return Result(src, REJECTED, "not a file")
    try:
        info = ffmpeg.probe(src)
    except ffmpeg.FFmpegError as e:
        return Result(src, REJECTED, f"not a readable audio file ({e})")
    except FileNotFoundError:
        return Result(src, REJECTED, "ffprobe is not installed")
    hashes = library_hashes(lib) if hashes is None else hashes
    staging = lib.data_dir / STAGING
    staging.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() if src.suffix else ".audio"
    if not re.fullmatch(r"\.[a-z0-9]{1,6}", ext):
        ext = ".audio"
    tmp = staging / f"{secrets.token_hex(8)}{ext}.partial"
    try:
        digest = _copy_verified(src, tmp)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        return Result(src, REJECTED, f"could not copy: {e}")
    if digest in hashes:
        tmp.unlink(missing_ok=True)
        dup = hashes[digest]
        return Result(src, DUPLICATE, f"already in the library as \"{dup.meta.title}\"", dup)
    title, date = title_and_date(src)
    rec = lib.create(title, "imported", source=src.name, state=READY)
    final = rec.folder / f"audio{ext}"
    os.replace(tmp, final)
    fsync_dir(rec.folder)
    rec.update(audio=final.name, sha256=digest, duration=_duration(final, info.duration),
               sample_rate=info.sample_rate, channels=info.channels,
               created=date.astimezone().isoformat(timespec="seconds"))
    hashes[digest] = rec
    log.info("imported %s as %s", src, rec.id)
    return Result(src, IMPORTED, f"imported ({info.codec}, {_fmt(rec.meta.duration)})", rec)


def _fmt(sec: float | None) -> str:
    if not sec:
        return "unknown length"
    sec = int(round(sec))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def import_paths(lib: Library, paths: Iterable[Path],
                 progress: Callable[[int, int, Path], None] | None = None,
                 auto_transcribe: bool | None = None) -> list[Result]:
    if auto_transcribe is None:
        auto_transcribe = features.auto_transcribe()
    files = expand(paths)
    hashes = library_hashes(lib)
    results = []
    for i, f in enumerate(files):
        if progress:
            progress(i, len(files), f)
        r = import_file(lib, f, hashes)
        if r.status == IMPORTED and auto_transcribe and r.recording:
            r.recording.request_transcription()
        results.append(r)
    if progress:
        progress(len(files), len(files), Path())
    return results

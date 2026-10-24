"""Import external audio files into the library, unchanged and verified, and the sound of video
files, extracted and verified (stdlib only)."""

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
# Screen recordings and video calls. .mp4 and .webm are in both sets: the streams decide.
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".flv", ".ts", ".mts", ".wmv"}
EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
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

_WA_ANDROID = re.compile(r"^(?P<kind>PTT|AUD)-(?P<d>\d{8})-WA(?P<n>\d+)", re.I)
_WA_DESKTOP = re.compile(
    r"^WhatsApp (?P<kind>Audio|Ptt|Voice Note)\s+(?P<d>\d{4}-\d{2}-\d{2})\s+(?:at|a las)\s+"
    r"(?P<h>\d{1,2})[.:](?P<m>\d{2})[.:](?P<s>\d{2})"
    r"(?:\s*(?P<ampm>[ap])\.?\s?m\.?)?", re.I)
_OBS = re.compile(r"^(?P<d>\d{4}-\d{2}-\d{2}) (?P<h>\d{2})-(?P<m>\d{2})-(?P<s>\d{2})$")  # OBS's default name


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
    m = _OBS.match(stem)
    if m and path.suffix.lower() in VIDEO_EXTENSIONS:
        try:
            dt = datetime.strptime(f"{m['d']} {m['h']}:{m['m']}:{m['s']}", "%Y-%m-%d %H:%M:%S")
            return f"Screen recording {dt:%Y-%m-%d %H:%M}", dt
        except ValueError:
            pass
    title = re.sub(r"[_]+", " ", stem).strip() or path.name
    return title, _mtime(path) or datetime.now()


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


# ---- discovery ----------------------------------------------------------------------------------

def expand(paths: Iterable[Path]) -> list[Path]:
    """Files as given; folders searched recursively for audio and video extensions. Order is stable."""
    out: list[Path] = []
    seen: set[Path] = set()
    for p in paths:
        p = Path(p)
        if p.is_dir():
            found = sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONS
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
    """Recordings by the hash of their audio file and, for those made from a video, of the video."""
    hashes = {}
    for rec in lib.all():
        if rec.meta.sha256:
            hashes[rec.meta.sha256] = rec
        video = (rec.meta.extracted_from or {}).get("sha256")
        if video:
            hashes[video] = rec
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


def import_file(lib: Library, src: Path, hashes: dict[str, Recording] | None = None,
                progress: Callable[[float], None] | None = None) -> Result:
    """Import one file. `progress` gets the fraction done while a video's sound is extracted."""
    src = Path(src)
    if not src.is_file():
        return Result(src, REJECTED, "not a file")
    try:
        info = ffmpeg.probe(src)
    except ffmpeg.NoAudio as e:
        return Result(src, REJECTED, str(e) if e.has_video else f"not a readable audio file ({e})")
    except ffmpeg.FFmpegError as e:
        return Result(src, REJECTED, f"not a readable audio file ({e})")
    except FileNotFoundError:
        return Result(src, REJECTED, "ffprobe is not installed")
    hashes = library_hashes(lib) if hashes is None else hashes
    staging = lib.data_dir / STAGING
    staging.mkdir(parents=True, exist_ok=True)
    if info.has_video:
        return _import_video(lib, src, info, hashes, staging, progress)
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


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _import_video(lib: Library, src: Path, info: ffmpeg.Probe, hashes: dict[str, Recording],
                  staging: Path, progress: Callable[[float], None] | None) -> Result:
    """Keep only the sound of a video: one track, copied when its codec allows, else encoded.

    The video is only read. Its hash is checked against the library before ffmpeg runs, so a
    meeting dropped twice costs one read (0.7 s for 1 GB, measured) instead of an extraction.
    """
    try:
        video_digest = _hash_file(src)
    except OSError as e:
        return Result(src, REJECTED, f"could not read: {e}")
    if video_digest in hashes:
        dup = hashes[video_digest]
        return Result(src, DUPLICATE, f"already in the library as \"{dup.meta.title}\"", dup)
    track = info.track
    ext, method, opts = ffmpeg.extraction_plan(track)
    tmp = staging / f"{secrets.token_hex(8)}{ext}.partial"
    try:
        ffmpeg.extract_audio(src, track, tmp, opts, progress)
        ffmpeg.verify_extraction(src, track, tmp, method)
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        digest = ffmpeg.sha256_file(tmp)
    except (ffmpeg.FFmpegError, OSError, subprocess.SubprocessError) as e:
        tmp.unlink(missing_ok=True)
        log.warning("extracting the sound of %s failed: %s", src, e)
        return Result(src, REJECTED, f"could not extract the sound ({e})")
    if digest in hashes:  # the same sound came in before as an audio file
        tmp.unlink(missing_ok=True)
        dup = hashes[digest]
        return Result(src, DUPLICATE, f"already in the library as \"{dup.meta.title}\"", dup)
    try:
        out = ffmpeg.probe(tmp)
    except ffmpeg.FFmpegError:
        out = info
    title, date = title_and_date(src)
    rec = lib.create(title, "imported", source=src.name, state=READY)
    final = rec.folder / f"audio{ext}"
    os.replace(tmp, final)
    fsync_dir(rec.folder)
    tracks = [t.index for t in info.tracks]
    rec.update(audio=final.name, sha256=digest, duration=_duration(final, out.duration),
               sample_rate=out.sample_rate, channels=out.channels,
               created=date.astimezone().isoformat(timespec="seconds"),
               extracted_from={"name": src.name, "sha256": video_digest, "size": src.stat().st_size,
                               "track": tracks.index(track.index) + 1, "method": method})
    hashes[digest] = hashes[video_digest] = rec
    log.info("imported the sound of %s as %s (%s %s)", src, rec.id, method, track.codec)
    how = f"{track.codec} sound kept as is" if method == ffmpeg.COPY else f"{track.codec} sound converted"
    return Result(src, IMPORTED, f"imported from video ({how}, {_fmt(rec.meta.duration)})", rec)


def _fmt(sec: float | None) -> str:
    if not sec:
        return "unknown length"
    sec = int(sec)  # truncate like every other duration display
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def import_paths(lib: Library, paths: Iterable[Path],
                 progress: Callable[..., None] | None = None,
                 auto_transcribe: bool | None = None) -> list[Result]:
    """Import files and folders. `progress(i, n, path)` is called before each file and, while a
    video's sound is extracted, again as `progress(i, n, path, fraction)`."""
    if auto_transcribe is None:
        auto_transcribe = features.auto_transcribe()
    files = expand(paths)
    hashes = library_hashes(lib)
    results = []
    for i, f in enumerate(files):
        if progress:
            progress(i, len(files), f)
        within = (lambda frac, i=i, f=f: progress(i, len(files), f, frac)) if progress else None
        r = import_file(lib, f, hashes, within)
        if r.status == IMPORTED and auto_transcribe and r.recording:
            from . import transcription

            transcription.request(lib, r.recording, start_worker=False)
        results.append(r)
    if progress:
        progress(len(files), len(files), Path())
    if auto_transcribe and any(r.status == IMPORTED for r in results):
        from . import transcription

        transcription.ensure_worker(lib)
    return results

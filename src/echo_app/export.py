"""Exporting audio and transcripts (no Qt)."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import align
from .audio import ffmpeg
from .library import Recording

TEXT_FORMATS = {".txt": "Text", ".md": "Markdown", ".srt": "SubRip subtitles", ".vtt": "WebVTT subtitles",
                ".json": "JSON with passage times"}


# Names Windows refuses for files whatever the extension.
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def suggested_name(rec: Recording, ext: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_.,()" else "_" for c in rec.meta.title).strip()
    safe = safe.rstrip(". ")[:120] or rec.id  # Windows drops trailing dots and spaces
    if safe.split(".")[0].lower() in _RESERVED:
        safe = f"_{safe}"
    return f"{safe}{ext}"


def export_audio(rec: Recording, dest: Path) -> Path:
    """Cropped span as lossless FLAC, or a copy of the original when there is no crop."""
    src = rec.audio_path
    if src is None or not src.exists():
        raise FileNotFoundError("This recording has no audio file.")
    dest = Path(dest)
    start, end = rec.effective_span()
    if not start and end is None:
        if dest.suffix.lower() != src.suffix.lower():
            dest = dest.with_suffix(src.suffix.lower())
        shutil.copyfile(src, dest)
        return dest
    dest = dest.with_suffix(".flac")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if end is not None:
        cmd += ["-t", f"{end - (start or 0.0):.3f}"]
    cmd += ["-vn", "-c:a", "flac", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ffmpeg.FFmpegError(r.stderr.strip()[-300:] or "export failed")
    return dest


def transcript_text(rec: Recording) -> str:
    return rec.text().strip() + "\n"


def stamp(sec: float) -> str:
    """m:ss, or h:mm:ss from an hour on (the margin and "copy with timestamps")."""
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _clock(sec: float, sep: str) -> str:
    ms = max(0, round(sec * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cues(rec: Recording) -> list[tuple[float, float, str, bool]]:
    """The text the user sees, cut into timed passages (edited text is aligned to the model's)."""
    t = rec.transcript() or {}
    segs = t.get("segments", [])
    c = rec.corrected()
    if c and len(c.get("segments", [])) == len(segs):
        segs = [{**sg, "text": tx} for sg, tx in zip(segs, c["segments"])]
    return align.cues(segs, rec.text())


def with_timestamps(rec: Recording) -> str:
    """One line per passage, "[m:ss] text", with a blank line where a paragraph starts."""
    lines = []
    for start, _end, text, paragraph in cues(rec):
        if paragraph and lines:
            lines.append("")
        lines.append(f"[{stamp(start)}] {text}")
    return "\n".join(lines) + "\n"


def to_srt(items) -> str:
    out = []
    for n, (start, end, text, _p) in enumerate(items, 1):
        out.append(f"{n}\n{_clock(start, ',')} --> {_clock(end, ',')}\n{text}\n")
    return "\n".join(out)


def to_vtt(items) -> str:
    out = ["WEBVTT\n"]
    for start, end, text, _p in items:
        out.append(f"{_clock(start, '.')} --> {_clock(end, '.')}\n{text}\n")
    return "\n".join(out)


def to_json(rec: Recording, items) -> str:
    t = rec.transcript() or {}
    data = {"id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "duration": rec.meta.duration,
            "language": t.get("language", "es"), "edited": rec.is_edited(),
            "segments": [{"start": round(a, 2), "end": round(b, 2), "text": text, "paragraph": p}
                         for a, b, text, p in items]}
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_transcript(rec: Recording, fmt: str) -> str:
    """The transcript in one of TEXT_FORMATS (".txt", ".md", ".srt", ".vtt", ".json")."""
    text = rec.text().strip()
    if fmt == ".md":
        try:
            when = datetime.fromisoformat(rec.meta.created).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            when = rec.meta.created
        return f"# {rec.meta.title}\n\n_{when}_\n\n{text}\n"
    if fmt == ".srt":
        return to_srt(cues(rec))
    if fmt == ".vtt":
        return to_vtt(cues(rec))
    if fmt == ".json":
        return to_json(rec, cues(rec))
    return text + "\n"


def export_transcript(rec: Recording, dest: Path) -> Path:
    dest = Path(dest)
    fmt = dest.suffix.lower()
    if fmt not in TEXT_FORMATS:
        dest = dest.with_suffix(".txt")
        fmt = ".txt"
    dest.write_text(render_transcript(rec, fmt), encoding="utf-8")
    return dest

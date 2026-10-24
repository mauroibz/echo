"""Exporting audio and transcripts (no Qt)."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .audio import ffmpeg
from .library import Recording


def suggested_name(rec: Recording, ext: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_.,()" else "_" for c in rec.meta.title).strip() or rec.id
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


def export_transcript(rec: Recording, dest: Path) -> Path:
    dest = Path(dest)
    text = rec.text().strip()
    if dest.suffix.lower() == ".md":
        try:
            when = datetime.fromisoformat(rec.meta.created).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            when = rec.meta.created
        body = f"# {rec.meta.title}\n\n_{when}_\n\n{text}\n"
    else:
        if dest.suffix.lower() != ".txt":
            dest = dest.with_suffix(".txt")
        body = text + "\n"
    dest.write_text(body, encoding="utf-8")
    return dest

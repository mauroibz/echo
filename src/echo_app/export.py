"""Exporting audio and transcripts (no Qt)."""

from __future__ import annotations

import json
import os
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


def speaker_name(rec: Recording, number: int | None) -> str | None:
    """The name for a speaker number: the user's, else "Speaker N"; None when speakers are off."""
    if number is None or rec.meta.speakers_off or not (rec.transcript() or {}).get("speakers"):
        return None
    return rec.meta.speakers.get(str(number)) or f"Speaker {number}"


def has_speakers(rec: Recording) -> bool:
    return not rec.meta.speakers_off and bool((rec.transcript() or {}).get("speakers"))


def cues(rec: Recording) -> list[tuple[float, float, str, bool, int | None]]:
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
    last = None
    for start, _end, text, paragraph, who in cues(rec):
        name = speaker_name(rec, who)
        if (paragraph or name != last) and lines:
            lines.append("")
        prefix = f"{name}: " if name and name != last else ""
        lines.append(f"[{stamp(start)}] {prefix}{text}")
        last = name
    return "\n".join(lines) + "\n"


def with_speakers(rec: Recording) -> str:
    """The text with "Name:" where the speaker changes, a new paragraph at each change."""
    paragraphs: list[str] = []
    last = None
    for _s, _e, text, paragraph, who in cues(rec):
        name = speaker_name(rec, who)
        if not paragraphs or paragraph or name != last:
            paragraphs.append(f"{name}: {text}" if name and name != last else text)
        else:
            paragraphs[-1] += " " + text
        last = name
    return "\n\n".join(paragraphs)


def to_srt(items, names=None) -> str:
    """SubRip; with `names` (speaker number -> name), a cue starts with "Name: " when the speaker changes."""
    out, last = [], None
    for n, (start, end, text, _p, who) in enumerate(items, 1):
        name = names.get(who) if names else None
        prefix = f"{name}: " if name and name != last else ""
        last = name
        out.append(f"{n}\n{_clock(start, ',')} --> {_clock(end, ',')}\n{prefix}{text}\n")
    return "\n".join(out)


def to_vtt(items, names=None) -> str:
    """WebVTT; with `names`, each cue carries its speaker as a voice tag (<v Name>)."""
    out = ["WEBVTT\n"]
    for start, end, text, _p, who in items:
        name = names.get(who) if names else None
        out.append(f"{_clock(start, '.')} --> {_clock(end, '.')}\n{f'<v {name}>' if name else ''}{text}\n")
    return "\n".join(out)


def to_json(rec: Recording, items) -> str:
    t = rec.transcript() or {}
    segs = []
    for a, b, text, p, who in items:
        seg = {"start": round(a, 2), "end": round(b, 2), "text": text, "paragraph": p}
        name = speaker_name(rec, who)
        if name:
            seg["speaker"] = name
        segs.append(seg)
    data = {"id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "duration": rec.meta.duration,
            "language": t.get("language", "es"), "edited": rec.is_edited(), "segments": segs}
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _names(rec: Recording) -> dict | None:
    if not has_speakers(rec):
        return None
    return {n: speaker_name(rec, n) for n in range(1, int(rec.transcript()["speakers"].get("count", 0)) + 1)}


def render_transcript(rec: Recording, fmt: str) -> str:
    """The transcript in one of TEXT_FORMATS (".txt", ".md", ".srt", ".vtt", ".json")."""
    text = (with_speakers(rec) if has_speakers(rec) else rec.text()).strip()
    if fmt == ".md":
        try:
            when = datetime.fromisoformat(rec.meta.created).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            when = rec.meta.created
        return f"# {rec.meta.title}\n\n_{when}_\n\n{text}\n"
    if fmt == ".srt":
        return to_srt(cues(rec), _names(rec))
    if fmt == ".vtt":
        return to_vtt(cues(rec), _names(rec))
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


# ---- Markdown notes and folder export ----------------------------------------------------------

AUDIO_COPY, AUDIO_LINK, AUDIO_NONE = "copy", "link", "none"
LEDGER = ".echo-export.json"


def _people(rec: Recording, text: str) -> list[str]:
    """Dictionary people named in the text, and named speakers once there are any."""
    from . import dictionary

    folded = dictionary.fold(text)
    names = [e.name for e in dictionary.current().entries
             if e.kind == dictionary.PEOPLE and any(dictionary.fold(s) in folded for s in e.spellings())]
    speakers = getattr(rec.meta, "speakers", None) or {}
    for name in speakers.values():
        if name and name not in names:
            names.append(name)
    return names


def to_markdown(rec: Recording, timestamps: bool = False, audio_link: str | None = None) -> str:
    """A note for a Markdown vault: title, date, length and tags, people, a link to the audio,
    and the text, with a heading at each marker and optionally each paragraph's time."""
    try:
        when = datetime.fromisoformat(rec.meta.created).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        when = rec.meta.created
    text = rec.text().strip()
    head = [f"# {rec.meta.title}", ""]
    line = f"_{when}_"
    if rec.meta.duration:
        line += f" · {stamp(rec.meta.duration)}"
    if rec.meta.tags:
        line += " · " + " ".join("#" + t.replace(" ", "-") for t in rec.meta.tags)
    head.append(line)
    people = _people(rec, text)
    if people:
        head.append(f"People: {', '.join(people)}")
    if audio_link:
        head.append(f"Audio: [{Path(audio_link).name}](<{audio_link}>)")
    if rec.meta.notes:
        head += ["", f"> {rec.meta.notes}"]
    body = _markdown_body(rec, text, timestamps)
    return "\n".join(head) + "\n\n" + body.strip() + "\n"


def _markdown_body(rec: Recording, text: str, timestamps: bool) -> str:
    items = cues(rec) if rec.transcript() else []
    if not items:
        return text
    paragraphs: list[tuple[float, list[str]]] = []
    last = None
    for start, _end, piece, para, who in items:
        name = speaker_name(rec, who)
        if para or not paragraphs or name != last:
            paragraphs.append((start, [f"**{name}:** {piece}" if name and name != last else piece]))
        else:
            paragraphs[-1][1].append(piece)
        last = name
    # Each marker heads the paragraph it falls in; text before the first marker gets "Inicio".
    headings: dict[int, list[str]] = {}
    for m in sorted(rec.meta.markers, key=lambda m: m["at"]):
        k = max((i for i, (start, _p) in enumerate(paragraphs) if start <= m["at"] + 0.01), default=0)
        headings.setdefault(k, []).append(f"## {stamp(m['at'])} {m.get('note') or ''}".rstrip())
    out = []
    if headings and min(headings) > 0:
        out.append("## 0:00 Inicio")
    for i, (start, pieces) in enumerate(paragraphs):
        out += headings.get(i, [])
        para = " ".join(pieces)
        out.append(f"[{stamp(start)}] {para}" if timestamps else para)
    return "\n\n".join(out)


def note_name(rec: Recording) -> str:
    """"2026-10-24 Charla con Ana.md"."""
    return f"{rec.meta.created[:10]} {suggested_name(rec, '.md')}"


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def export_folder(recs, dest: Path, timestamps: bool = False, audio: str = AUDIO_LINK) -> dict[str, int]:
    """One Markdown note per recording in `dest`, skipping notes that are up to date.

    A ledger in the folder maps recording ids to the note's file and content hash, so renamed
    recordings replace their old note and only changed notes are rewritten. Returns counts of
    "written", "unchanged" and "removed" (old names of renamed recordings).
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        ledger = json.loads((dest / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ledger = {}
    taken = {v.get("file") for k, v in ledger.items()}
    counts = {"written": 0, "unchanged": 0, "removed": 0}
    for rec in recs:
        if not rec.text().strip() and not rec.meta.notes:
            continue  # nothing to read yet
        entry = ledger.get(rec.id, {})
        name = entry.get("file") if entry.get("file") == note_name(rec) else note_name(rec)
        if name != entry.get("file"):
            base, n = name[:-3], 2
            while name in taken and name != entry.get("file"):
                name, n = f"{base} {n}.md", n + 1
        link = None
        src = rec.audio_path
        if audio != AUDIO_NONE and src is not None and src.exists():
            if audio == AUDIO_COPY:
                audio_dest = dest / "audio" / f"{rec.id}{src.suffix.lower()}"
                if not audio_dest.exists() or audio_dest.stat().st_size != src.stat().st_size:
                    audio_dest.parent.mkdir(exist_ok=True)
                    shutil.copyfile(src, audio_dest)
                link = f"audio/{audio_dest.name}"
            else:
                link = Path(os.path.relpath(src, dest)).as_posix()
        note = to_markdown(rec, timestamps, link).encode("utf-8")
        sha = _sha(note)
        old = entry.get("file")
        if old and old != name and (dest / old).exists():
            (dest / old).unlink()
            counts["removed"] += 1
        if entry.get("sha") == sha and old == name and (dest / name).exists():
            counts["unchanged"] += 1
            continue
        (dest / name).write_bytes(note)
        ledger[rec.id] = {"file": name, "sha": sha}
        taken.add(name)
        counts["written"] += 1
    (dest / LEDGER).write_text(json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return counts

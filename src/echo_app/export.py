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


def _md_tag(tag: str) -> str:
    """A tag as Markdown tools read it: no spaces, and a category nested with "/" (`#client/Acme`)."""
    return "#" + tag.replace(" ", "-").replace(":", "/")


def speaker_name(rec: Recording, number: int | None) -> str | None:
    """The name for a speaker number: the user's, else "Speaker N"; None when speakers are off."""
    if number is None or rec.meta.speakers_off or not (rec.transcript() or {}).get("speakers"):
        return None
    number = rec.speaker(number)
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
    return align.cues(segs, rec.text(), t.get("language", "es"), rec.fixes(t))


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
    return {n: speaker_name(rec, n) for n in rec.speaker_numbers()}


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


# ---- linked sets ---------------------------------------------------------------------------------
# A set exports as one transcript: a heading per part and times on the set's timeline (the parts'
# cropped spans laid end to end), so subtitles of the set follow its continuous playback.

def _when(created: str) -> str:
    try:
        return datetime.fromisoformat(created).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return created


def part_heading(rec: Recording) -> str:
    """"Nota 2 · 2026-10-23 14:04 · 1:58"."""
    bits = [rec.meta.title, _when(rec.meta.created)]
    if rec.meta.duration:
        from .sets import span

        bits.append(stamp(span(rec)[1]))
    return " · ".join(bits)


def set_cues(parts) -> list[tuple[float, float, str, bool, str | None, int]]:
    """Every part's passages on the set timeline: (start, end, text, paragraph, speaker name, part)."""
    from .sets import timeline

    out = []
    for k, p in enumerate(timeline(parts)):
        if not p.rec.transcript():
            continue
        for a, b, text, para, who in cues(p.rec):
            out.append((p.to_set(a), p.to_set(b), text, para, speaker_name(p.rec, who), k))
    return out


def _set_text(parts, timestamps: bool = False, markdown: bool = False) -> str:
    from .sets import timeline

    blocks = []
    for p in timeline(parts):
        rec = p.rec
        head = f"## {rec.meta.title}\n\n_{part_heading(rec).split(' · ', 1)[1]}_" if markdown else part_heading(rec)
        if timestamps and rec.transcript():
            lines, last = [], None
            for a, _b, text, para, who in cues(rec):
                name = speaker_name(rec, who)
                if (para or name != last) and lines:
                    lines.append("")
                lines.append(f"[{stamp(p.to_set(a))}] {f'{name}: ' if name and name != last else ''}{text}")
                last = name
            body = "\n".join(lines)
        else:
            body = (with_speakers(rec) if has_speakers(rec) else rec.text()).strip()
        blocks.append(f"{head}\n\n{body}" if body else head)
    return "\n\n".join(blocks) + "\n"


def set_with_timestamps(parts) -> str:
    return _set_text(parts, timestamps=True)


def render_set(title: str, parts, fmt: str, set_id: str = "") -> str:
    """A linked set in one of TEXT_FORMATS."""
    if fmt == ".md":
        span_text = ""
        if parts:
            span_text = f"_{_when(parts[0].meta.created)} – {_when(parts[-1].meta.created)}_\n\n"
        return f"# {title}\n\n{span_text}{_set_text(parts, markdown=True)}"
    if fmt in (".srt", ".vtt"):
        items = [(a, b, text, para, name) for a, b, text, para, name, _k in set_cues(parts)]
        names = {n: n for *_x, n in items if n}
        return to_srt(items, names) if fmt == ".srt" else to_vtt(items, names)
    if fmt == ".json":
        from .sets import timeline

        tl = timeline(parts)
        segs = []
        for a, b, text, para, name, k in set_cues(parts):
            seg = {"start": round(a, 2), "end": round(b, 2), "text": text, "paragraph": para, "part": k}
            if name:
                seg["speaker"] = name
            segs.append(seg)
        data = {"id": set_id, "title": title,
                "parts": [{"id": p.rec.id, "title": p.rec.meta.title, "created": p.rec.meta.created,
                           "offset": round(p.offset, 2), "length": round(p.length, 2),
                           "edited": p.rec.is_edited()} for p in tl],
                "segments": segs}
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return _set_text(parts)


def export_set(title: str, parts, dest: Path, set_id: str = "") -> Path:
    dest = Path(dest)
    fmt = dest.suffix.lower()
    if fmt not in TEXT_FORMATS:
        dest, fmt = dest.with_suffix(".txt"), ".txt"
    dest.write_text(render_set(title, parts, fmt, set_id), encoding="utf-8")
    return dest


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
        line += " · " + " ".join(_md_tag(t) for t in rec.meta.tags)
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


_EXPORT_LOCK = __import__("threading").Lock()  # one export at a time: each rewrites the ledger


def _file_sha(path: Path) -> str | None:
    try:
        return _sha(path.read_bytes())
    except OSError:
        return None


def export_folder(recs, dest: Path, timestamps: bool = False, audio: str = AUDIO_LINK) -> dict[str, int]:
    """One Markdown note per recording in `dest`, skipping notes that are up to date.

    A ledger in the folder maps recording ids to the note's file and the hash of what was
    written, so renamed recordings replace their old note and only changed notes are rewritten.
    Echo only ever replaces or removes a file it wrote and nobody changed since: a note the user
    edited is left as it is (and no longer updated), and an existing file with the same name gets
    a numbered name instead. Returns counts of "written", "unchanged", "removed" (old notes of
    renamed recordings) and "kept" (notes the user changed).
    """
    with _EXPORT_LOCK:
        return _export_folder(recs, Path(dest), timestamps, audio)


def _audio_link(rec: Recording, dest: Path, audio: str) -> str | None:
    src = rec.audio_path
    if audio == AUDIO_NONE or src is None or not src.exists():
        return None
    if audio == AUDIO_COPY:
        audio_dest = dest / "audio" / f"{rec.id}{src.suffix.lower()}"
        if not audio_dest.exists() or audio_dest.stat().st_size != src.stat().st_size:
            audio_dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(src, audio_dest)
        return f"audio/{audio_dest.name}"
    return Path(os.path.relpath(src, dest)).as_posix()


def set_to_markdown(title: str, parts, timestamps: bool = False, audio_links=None) -> str:
    """A linked set as one note: each part a section, its markers one level below."""
    from .sets import timeline, total

    tl = timeline(parts)
    first, last = parts[0].meta.created, parts[-1].meta.created
    span = _when(first) + (f" – {_when(last)[11:]}" if first[:10] == last[:10] else f" – {_when(last)}")
    tags: list[str] = []
    for r in parts:
        tags += [t for t in r.meta.tags if t not in tags]
    line = f"_{span}_ · {stamp(total(tl))} · {len(parts)} parts"
    if tags:
        line += " · " + " ".join(_md_tag(t) for t in tags)
    head = [f"# {title}", "", line]
    people: list[str] = []
    for r in parts:
        people += [n for n in _people(r, r.text()) if n not in people]
    if people:
        head.append(f"People: {', '.join(people)}")
    links = [lk for lk in (audio_links or []) if lk]
    if links:
        head.append("Audio: " + ", ".join(f"[{k}](<{lk}>)" for k, lk in enumerate(links, 1)))
    sections = []
    for k, (r, p) in enumerate(zip(parts, tl), 1):
        body = _markdown_body(r, r.text().strip(), timestamps).replace("\n## ", "\n### ")
        if body.startswith("## "):
            body = "#" + body
        sec = [f"## {k}. {r.meta.title}", "", f"_{_when(r.meta.created)} · {stamp(p.length)}_"]
        if r.meta.notes:
            sec += ["", f"> {r.meta.notes}"]
        if body.strip():
            sec += ["", body.strip()]
        sections.append("\n".join(sec))
    return "\n".join(head) + "\n\n" + "\n\n".join(sections) + "\n"


def set_note_name(title: str, parts) -> str:
    from types import SimpleNamespace

    return f"{parts[0].meta.created[:10]} {suggested_name(SimpleNamespace(meta=SimpleNamespace(title=title), id='set'), '.md')}"


def _export_folder(recs, dest: Path, timestamps: bool, audio: str) -> dict[str, int]:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        ledger = json.loads((dest / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ledger = {}
    owner = {v.get("file"): rid for rid, v in ledger.items()}
    counts = {"written": 0, "unchanged": 0, "removed": 0, "kept": 0}
    recs = list(recs)
    # A linked set is one note; its parts get none of their own.
    groups: dict[str, tuple] = {}
    member_of: dict[str, str] = {}
    live_sets: set[str] = set()
    if recs:
        from . import sets
        from .library import Library

        library = Library(recs[0].folder.parent.parent)
        for st in sets.load_all(library):
            parts = sets.present(library, st)
            if len(parts) >= 2:
                live_sets.add(st.id)
                for r in parts:
                    member_of[r.id] = st.id
                groups[st.id] = (st, parts)

    def drop(key: str):
        entry = ledger.get(key)
        if not entry:
            return
        old = entry.get("file")
        if old and (dest / old).exists() and _file_sha(dest / old) != entry.get("sha"):
            return  # changed by the user: theirs
        if old and (dest / old).exists():
            (dest / old).unlink()
            counts["removed"] += 1
        owner.pop(old, None)
        ledger.pop(key, None)

    items = []
    done_sets: set[str] = set()
    for rec in recs:
        sid = member_of.get(rec.id)
        if sid is None:
            items.append((rec.id, rec, None))
        else:
            drop(rec.id)  # a note written before the recording was linked
            if sid not in done_sets:
                done_sets.add(sid)
                items.append((sid, None, groups[sid]))
    for key in [k for k in ledger if k.startswith("set_") and k not in live_sets]:
        drop(key)  # a set that was unlinked
    for key, rec, group in items:
        if rec is not None:
            if not rec.text().strip() and not rec.meta.notes:
                continue  # nothing to read yet
        elif not any(r.text().strip() or r.meta.notes for r in group[1]):
            continue
        entry = ledger.get(key, {})
        old = entry.get("file")
        untouched = bool(old) and _file_sha(dest / old) == entry.get("sha")
        if old and (dest / old).exists() and not untouched:
            counts["kept"] += 1  # the user changed this note: it is theirs now
            continue
        name = note_name(rec) if rec is not None else set_note_name(group[0].title, group[1])
        if name != old:
            base, n = name[:-3], 2
            while (dest / name).exists() or owner.get(name, key) != key:
                name, n = f"{base} {n}.md", n + 1
        if rec is not None:
            note = to_markdown(rec, timestamps, _audio_link(rec, dest, audio)).encode("utf-8")
        else:
            st, parts = group
            note = set_to_markdown(st.title, parts, timestamps,
                                   [_audio_link(r, dest, audio) for r in parts]).encode("utf-8")
        sha = _sha(note)
        if old and old != name and untouched:
            (dest / old).unlink()
            owner.pop(old, None)
            counts["removed"] += 1
        if old == name and untouched and entry.get("sha") == sha:
            counts["unchanged"] += 1
            continue
        (dest / name).write_bytes(note)
        ledger[key] = {"file": name, "sha": sha}
        owner[name] = key
        counts["written"] += 1
    (dest / LEDGER).write_text(json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return counts

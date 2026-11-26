"""A bundle: chosen parts of chosen recordings as Markdown, to paste into an assistant or zip (no Qt).

Each recording is a note with its header (title, date, length, tags, people, the user's notes) and
the parts asked for under a heading each. Echo's own part is the transcript; extensions offer more
through the `bundle_parts` hook (Studio: the summary and the action items). A recording with none
of the chosen parts is left out, so a bundle never carries an empty note.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from . import export, extensions
from .fsutil import atomic_write_bytes
from .library import Recording

TRANSCRIPT = "transcript"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)  # the same bundle is the same bytes whenever it is written


def _transcript_heading(rec: Recording) -> str:
    lang = (rec.transcript() or {}).get("language") or rec.meta.language or "es"
    return "Transcripción" if lang == "es" else "Transcript"


def _transcript(rec: Recording, timestamps: bool) -> str:
    if not rec.text().strip():
        return ""
    if rec.transcript():
        if timestamps:
            return export.with_timestamps(rec).strip()
        if export.has_speakers(rec):
            return export.with_speakers(rec).strip()
    return rec.text().strip()


def _offered(rec: Recording) -> list[tuple[str, str, str, str]]:
    """(key, label, heading, markdown) of each part an extension has for the recording."""
    return [(str(k), str(label), str(heading), str(md).strip())
            for k, label, heading, md in extensions.gather("bundle_parts", rec) if str(md).strip()]


def available(recs) -> list[tuple[str, str]]:
    """(key, label) of each part at least one of the recordings has, the transcript first. Cheap
    (no transcript is laid out), so a dialog can ask for a large selection."""
    found: dict[str, str] = {}
    for rec in recs:
        if rec.text().strip():
            found.setdefault(TRANSCRIPT, "Transcript")
        for key, label, _h, _md in _offered(rec):
            found.setdefault(key, label)
    return sorted(found.items(), key=lambda kv: kv[0] != TRANSCRIPT)  # stable: the rest keep their order


def render(rec: Recording, keys=None, timestamps: bool = False) -> str:
    """One recording's note with the parts in `keys` (None: all it has); "" when it has none of them."""
    # What extensions offer first, the transcript last: the longest part, and the one an assistant
    # needs least near the question that follows the paste.
    parts = [(h, md) for k, _l, h, md in _offered(rec) if keys is None or k in keys]
    if keys is None or TRANSCRIPT in keys:
        body = _transcript(rec, timestamps)
        if body:
            parts.append((_transcript_heading(rec), body))
    if not parts:
        return ""
    return export.note_head(rec) + "\n\n" + "".join(f"## {h}\n\n{md}\n\n" for h, md in parts).rstrip() + "\n"


def notes(recs, keys=None, timestamps: bool = False) -> list[tuple[Recording, str]]:
    """Each recording with something to say, with its note."""
    out = []
    for rec in recs:
        md = render(rec, keys, timestamps)
        if md:
            out.append((rec, md))
    return out


def text(recs, keys=None, timestamps: bool = False) -> str:
    """Every note one after another: what goes to the clipboard."""
    return "\n".join(md for _rec, md in notes(recs, keys, timestamps))


def words(s: str) -> int:
    return len(s.split())


def write_zip(recs, dest: Path, keys=None, timestamps: bool = False) -> int:
    """A zip with one Markdown note per recording; returns how many. Nothing is written when no
    recording has any of the parts."""
    return zip_notes(notes(recs, keys, timestamps), dest)


def zip_notes(items: list[tuple[Recording, str]], dest: Path) -> int:
    """`write_zip` for notes already laid out (as `notes` returns them)."""
    if not items:
        return 0
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rec, md in items:
            name = export.note_name(rec)
            if name.lower() in used:  # two recordings of one day with one title
                name = f"{name[:-3]} ({rec.id}).md"
            used.add(name.lower())
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, md.encode("utf-8"))
    atomic_write_bytes(Path(dest), buf.getvalue())
    return len(items)


def expand(lib, ids) -> list[Recording]:
    """The recordings for ids of recordings and linked sets (a set: its parts, in order), each once.
    Raises KeyError naming an id that is neither."""
    from . import sets

    out: dict[str, Recording] = {}
    for i in ids:
        if sets.is_set_id(i):
            st = sets.get(lib, i)
            if st is None:
                raise KeyError(i)
            found = sets.present(lib, st)
        else:
            rec = lib.get(i)
            if rec is None:
                raise KeyError(i)
            found = [rec]
        for rec in found:
            out.setdefault(rec.id, rec)
    return list(out.values())

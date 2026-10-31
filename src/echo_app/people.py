"""People: a profile per person (notes, tags) as files in the data folder, and everyone Echo knows.

A person is anyone in the dictionary's people, anyone with a profile file, and any name given to
a speaker. Profiles live next to the recordings (``people/<slug>.json``) because notes about a
person are the user's content, backed up and synced with what they describe; aliases stay in the
dictionary, where transcription reads them, and voices in ``voices.json``. Nothing is written
until there is something to keep: an empty profile has no file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import dictionary
from .fsutil import atomic_write_json, read_json
from .library import Library, clean_tag, fold_tag

FOLDER = "people"


@dataclass
class Profile:
    name: str
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    email: str = ""  # matches the person to a calendar's attendees and to an extension's records

    @property
    def empty(self) -> bool:
        return not self.notes.strip() and not self.tags and not self.email


@dataclass
class Person:
    name: str
    recordings: int = 0
    seconds: float = 0.0
    last: str | None = None  # when the newest recording they speak in was made
    has_voice: bool = False
    in_dictionary: bool = False
    profile: Profile | None = None


def folder(lib: Library) -> Path:
    return lib.data_dir / FOLDER


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", fold_tag(name)).strip("-") or "person"


def _read(path: Path) -> Profile | None:
    try:
        d = read_json(path)
        return Profile(str(d["name"]), str(d.get("notes") or ""), [str(t) for t in d.get("tags") or []],
                       clean_email(str(d.get("email") or "")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _path(lib: Library, name: str) -> Path:
    """The person's file: their slug, or a numbered one if another name has the same slug."""
    base, n = _slug(name), 1
    while True:
        p = folder(lib) / (f"{base}.json" if n == 1 else f"{base}-{n}.json")
        prof = _read(p) if p.exists() else None
        if prof is None or fold_tag(prof.name) == fold_tag(name):
            return p
        n += 1


def load(lib: Library, name: str) -> Profile:
    p = _path(lib, name)
    return (_read(p) if p.exists() else None) or Profile(name)


def save(lib: Library, profile: Profile) -> None:
    """Write the profile; an empty one removes its file."""
    profile.tags = [t for t in dict.fromkeys(clean_tag(t) for t in profile.tags) if t]
    p = _path(lib, profile.name)
    if profile.empty:
        p.unlink(missing_ok=True)
        return
    profile.email = clean_email(profile.email)
    atomic_write_json(p, {"name": profile.name, "notes": profile.notes.strip(), "tags": profile.tags,
                          "email": profile.email}, mkdir=True)


def clean_email(s: str) -> str:
    """An address as compared: trimmed and lower case, without a display name or angle brackets;
    "" when it is not an address."""
    m = re.search(r"[^\s<>\"':]+@[^\s<>\"':]+\.[^\s<>\"':]+", s or "")  # a "mailto:" is left out
    return m.group(0).lower().strip(".,;") if m else ""


def by_email(lib: Library, email: str) -> Profile | None:
    """The profile with this email, if a person has it."""
    want = clean_email(email)
    return next((p for p in profiles(lib) if want and p.email == want), None)


def profiles(lib: Library) -> list[Profile]:
    try:
        paths = sorted(folder(lib).glob("*.json"))
    except OSError:
        return []
    return [p for p in (_read(x) for x in paths) if p is not None]


def everyone(lib: Library, index) -> list[Person]:
    """Every person, most recordings first, then by name. `index` is an up-to-date Index."""
    out: dict[str, Person] = {}

    def person(name: str) -> Person:
        return out.setdefault(fold_tag(name), Person(name))

    for e in dictionary.current().entries:
        if e.kind == dictionary.PEOPLE:
            person(e.name).in_dictionary = True
    for prof in profiles(lib):
        person(prof.name).profile = prof
    for name, _n in index.speakers():
        person(name)
    for r in index.db.execute("SELECT s.name_folded, COUNT(DISTINCT s.id) n, SUM(s.seconds) secs, MAX(r.created) last "
                              "FROM speakers s JOIN recordings r ON r.id = s.id GROUP BY s.name_folded"):
        p = out.get(r["name_folded"])
        if p is not None:
            p.recordings, p.seconds, p.last = r["n"], float(r["secs"] or 0), r["last"]
    voices = {fold_tag(n) for n in dictionary.voices()}
    for key, p in out.items():
        p.has_voice = key in voices
    return sorted(out.values(), key=lambda p: (-p.recordings, fold_tag(p.name)))


def recordings_of(index, name: str) -> list[dict]:
    """The recordings a person speaks in, newest first: id, title, created, seconds, number."""
    rows = index.db.execute(
        "SELECT r.id, r.title, r.created, s.seconds, s.number FROM speakers s JOIN recordings r ON r.id = s.id "
        "WHERE s.name_folded = ? ORDER BY r.created DESC", (fold_tag(name),))
    return [dict(r) for r in rows]

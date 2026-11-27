"""Collections: recordings filed apart from the day-to-day list (stdlib only).

A batch dropped in together (a round of interviews, a course, a client's archive) is filed under a
name and shown only when that collection is opened, so the list stays the day's work however much
is imported. A recording is in one collection or in none, and the name is a field of its
meta.json: there is no file for a collection, so one exists while a recording names it and
nothing can point at a collection that is not there. Names compare without case or accents, as
tags do; the spelling shown is the one most of its recordings carry.
"""

from __future__ import annotations

from dataclasses import dataclass

from .library import T_DONE, Library, Recording, fold_tag

NAME_MAX = 60


def clean(name: str) -> str:
    """A name as stored: one line, up to NAME_MAX characters; "" if nothing is left."""
    return " ".join(str(name or "").split())[:NAME_MAX].strip()


def same(a: str, b: str) -> bool:
    return fold_tag(clean(a)) == fold_tag(clean(b))


@dataclass
class Collection:
    name: str
    recordings: list[Recording]  # newest first

    @property
    def transcribed(self) -> int:
        return sum(1 for r in self.recordings if r.transcript_status() == T_DONE)


def group(recs) -> list[Collection]:
    """The collections among `recs`, by name."""
    by: dict[str, list[Recording]] = {}
    for rec in recs:
        if clean(rec.meta.collection):
            by.setdefault(fold_tag(clean(rec.meta.collection)), []).append(rec)
    out = []
    for members in by.values():
        spellings = [clean(r.meta.collection) for r in members]
        name = max(sorted(set(spellings)), key=spellings.count)
        out.append(Collection(name, sorted(members, key=lambda r: r.meta.created, reverse=True)))
    return sorted(out, key=lambda c: fold_tag(c.name))


def all_of(lib: Library) -> list[Collection]:
    return group(lib.all())


def get(lib: Library, name: str) -> Collection | None:
    return next((c for c in all_of(lib) if same(c.name, name)), None)


def spelling(lib: Library, name: str) -> str:
    """`name` as the collection it means is already spelled, else cleaned."""
    c = get(lib, name)
    return c.name if c is not None else clean(name)


def file(recs, name: str) -> int:
    """Put the recordings in the collection `name` ("" takes them out). Returns how many changed."""
    name = clean(name)
    n = 0
    for rec in recs:
        if rec.meta.collection != name:
            rec.update(collection=name)
            n += 1
    return n


def rename(lib: Library, old: str, new: str) -> int:
    """Rename a collection; renaming onto another one's name joins them. Returns how many recordings."""
    c = get(lib, old)
    new = clean(new)
    if c is None or not new:
        return 0
    file(c.recordings, new if same(old, new) else spelling(lib, new))
    return len(c.recordings)


def dissolve(lib: Library, name: str) -> int:
    """Back to the day-to-day list, every recording of it; nothing is deleted."""
    c = get(lib, name)
    return file(c.recordings, "") if c is not None else 0

"""Linked sets: recordings that belong together (a burst of voice notes), read and played as one.

A set is one small file, ``<data>/sets/<set id>.json``::

    {"id": "set_2026-10-24T13-40-00_ab12", "title": "Audios de Lucía", "title_auto": true,
     "members": ["2026-10-23T14-02-11_9f3e", "2026-10-23T14-04-30_77a1"],
     "created": "2026-10-24T13:40:00-03:00"}

The member order is the reading and playing order, and nothing else records membership: the
members' folders are never touched by linking, so a recording folder still moves on its own.
Members that are missing (in the trash, not synced yet) are skipped, not removed, so a restored
recording comes back into its set. One recording is in at most one set; if two files claim the
same recording (a sync conflict), the most recently written file wins and the other's claim is
ignored until that file is next written, which drops it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .fsutil import atomic_write_json, read_json
from .library import Library, Recording, auto_title, new_id

SETS = "sets"
PREFIX = "set_"


def is_set_id(sid: str) -> bool:
    return sid.startswith(PREFIX)


@dataclass
class LinkedSet:
    id: str
    title: str
    members: list[str]  # the effective members, claims lost to a newer file removed
    created: str = ""
    title_auto: bool = True
    mtime: float = 0.0
    claimed: list[str] = field(default_factory=list)  # members as written in the file


def _dir(library: Library) -> Path:
    return library.data_dir / SETS


def _path(library: Library, sid: str) -> Path:
    return _dir(library) / f"{sid}.json"


def _read(path: Path) -> LinkedSet | None:
    try:
        d = read_json(path)
        members = [str(m) for m in d.get("members", []) if m]
        return LinkedSet(id=str(d["id"]), title=str(d.get("title") or ""), members=list(dict.fromkeys(members)),
                         created=str(d.get("created") or ""), title_auto=bool(d.get("title_auto", True)),
                         mtime=path.stat().st_mtime, claimed=members)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def load_all(library: Library) -> list[LinkedSet]:
    """Every set, each recording claimed by its newest file only."""
    try:
        paths = [p for p in _dir(library).iterdir() if p.suffix == ".json" and is_set_id(p.stem)]
    except FileNotFoundError:
        return []
    sets = [s for s in (_read(p) for p in paths) if s is not None]
    sets.sort(key=lambda s: (s.mtime, s.id), reverse=True)
    taken: set[str] = set()
    for s in sets:
        s.members = [m for m in s.members if m not in taken]
        taken.update(s.members)
    return sets


def membership(sets: list[LinkedSet]) -> dict[str, str]:
    """Recording id -> set id."""
    return {m: s.id for s in sets for m in s.members}


def get(library: Library, sid: str) -> LinkedSet | None:
    return next((s for s in load_all(library) if s.id == sid), None)


def set_of(library: Library, rid: str) -> LinkedSet | None:
    return next((s for s in load_all(library) if rid in s.members), None)


def present(library: Library, s: LinkedSet) -> list[Recording]:
    """The members whose folders are there, in set order."""
    return [r for r in (library.get(m) for m in s.members) if r is not None]


def _save(library: Library, s: LinkedSet) -> None:
    atomic_write_json(_path(library, s.id), {"id": s.id, "title": s.title, "title_auto": s.title_auto,
                                             "members": s.members, "created": s.created}, mkdir=True)
    s.claimed = list(s.members)


def _delete(library: Library, sid: str) -> None:
    try:
        os.unlink(_path(library, sid))
    except FileNotFoundError:
        pass


def _take_out(library: Library, rids: set[str], keep: str | None = None) -> None:
    """Remove recordings from every set but `keep`; a set left with fewer than two is dissolved."""
    for s in load_all(library):
        if s.id == keep or not rids & set(s.members):
            continue
        s.members = [m for m in s.members if m not in rids]
        if len(s.members) < 2:
            _delete(library, s.id)
        else:
            _save(library, s)


def _default_title(first: Recording | None, n: int) -> str:
    if first is None:
        return "Linked recordings"
    return f"{first.meta.title} (+{n - 1})" if n > 1 else first.meta.title


def link(library: Library, ids: list[str], title: str | None = None) -> LinkedSet:
    """Link recordings (and sets) into one set and return it.

    Without a set among `ids`, a new set holds the recordings in date order. With one set, the
    other recordings are added at its end in date order; with several, the first set named takes
    the others' members after its own. A recording in another set moves to this one.
    """
    sets = load_all(library)
    by_id = {s.id: s for s in sets}
    named_sets = [by_id[i] for i in ids if i in by_id]
    if any(is_set_id(i) and i not in by_id for i in ids):
        raise KeyError(next(i for i in ids if is_set_id(i) and i not in by_id))
    recs = []
    for i in ids:
        if i in by_id:
            continue
        rec = library.get(i)
        if rec is None:
            raise KeyError(i)
        recs.append(rec)
    recs.sort(key=lambda r: (r.meta.created, r.id))
    if named_sets:
        target = named_sets[0]
        extra = [m for s in named_sets[1:] for m in s.members] + [r.id for r in recs]
        for s in named_sets[1:]:
            _delete(library, s.id)
        target.members = list(dict.fromkeys(target.members + [m for m in extra if m not in target.members]))
    else:
        if len(recs) < 2:
            raise ValueError("Linking needs at least two recordings.")
        now = datetime.now().astimezone()
        target = LinkedSet(id=PREFIX + new_id(now), title="", members=[r.id for r in recs],
                           created=now.isoformat(timespec="seconds"))
        target.title = _default_title(recs[0], len(recs))
    if title:
        target.title, target.title_auto = title, False
    _take_out(library, set(target.members), keep=target.id)
    _save(library, target)
    refresh_title(library, target)
    return target


def move(library: Library, sid: str, rid: str, index: int) -> LinkedSet:
    """Put `rid` at position `index` of the set (reordering, or adding it from elsewhere)."""
    s = get(library, sid)
    if s is None:
        raise KeyError(sid)
    if library.get(rid) is None:
        raise KeyError(rid)
    members = [m for m in s.members if m != rid]
    members.insert(max(0, min(index, len(members))), rid)
    s.members = members
    _take_out(library, {rid}, keep=s.id)
    _save(library, s)
    return s


def unlink(library: Library, rid: str) -> None:
    """Take one recording out of its set; a set left with one member is dissolved."""
    _take_out(library, {rid})


def dissolve(library: Library, sid: str) -> None:
    _delete(library, sid)


def rename(library: Library, sid: str, title: str) -> None:
    s = get(library, sid)
    if s is not None and title.strip():
        s.title, s.title_auto = title.strip(), False
        _save(library, s)


def refresh_title(library: Library, s: LinkedSet | None) -> None:
    """A set not renamed takes its title from the first part's first sentence once there is text."""
    if s is None or not s.title_auto:
        return
    parts = present(library, s)
    if not parts:
        return
    sentence = auto_title(parts[0].text())
    title = f"{sentence} (+{len(parts) - 1})" if sentence else _default_title(parts[0], len(parts))
    if title != s.title:
        s.title = title
        _save(library, s)


def cleanup(library: Library) -> int:
    """Remove set files with no present members (after `rescan`). Returns how many."""
    n = 0
    for s in load_all(library):
        if not s.claimed or not any(library.get(m) for m in s.claimed):
            _delete(library, s.id)
            n += 1
    return n


# ---- the set's timeline --------------------------------------------------------------------------

@dataclass
class Part:
    rec: Recording
    offset: float  # where the part starts on the set's timeline, seconds
    start: float  # the part's crop start in its own audio
    length: float  # its cropped length

    def to_set(self, t: float) -> float:
        """A time in the part's audio -> the set's timeline."""
        return self.offset + (t - self.start)

    def to_part(self, t: float) -> float:
        return self.start + (t - self.offset)


def span(rec: Recording) -> tuple[float, float]:
    start, end = rec.effective_span()
    if end is None:
        end = rec.meta.duration or 0.0
    return start, max(0.0, end - start)


def timeline(parts: list[Recording]) -> list[Part]:
    out, t = [], 0.0
    for rec in parts:
        start, length = span(rec)
        out.append(Part(rec, t, start, length))
        t += length
    return out


def part_at(tl: list[Part], t: float) -> int:
    """The index of the part playing at set time `t` (the last one past the end)."""
    for i, p in enumerate(tl):
        if t < p.offset + p.length:
            return i
    return max(0, len(tl) - 1)


def total(tl: list[Part]) -> float:
    return sum(p.length for p in tl)


def summary(s: LinkedSet, parts: list[Recording]) -> str:
    """"3 parts · 6:12"."""
    from .export import stamp

    return f"{len(parts)} parts · {stamp(total(timeline(parts)))}"

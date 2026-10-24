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

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .fsutil import atomic_write_json, read_json
from .library import Library, Recording, auto_title, new_id

log = logging.getLogger(__name__)

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


@contextmanager
def _locked(library: Library):
    """One writer of set files at a time: the window links while the worker retitles a set,
    and each reads a file before rewriting it."""
    from . import locks

    folder = _dir(library)
    folder.mkdir(parents=True, exist_ok=True)
    lock = locks.acquire(folder / ".lock", wait=5.0)
    if lock is None:
        log.warning("set files are locked by another process; writing anyway")
    try:
        yield
    finally:
        if lock is not None:
            lock.close()


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


def _order(rec: Recording) -> tuple:
    """Date order; Android voice notes of one day all carry that date, so their number decides."""
    key = whatsapp_key(rec)
    return rec.meta.created, key[2] if key and key[0] == "android" else 0.0, rec.id


def _default_title(first: Recording | None, n: int) -> str:
    if first is None:
        return "Linked recordings"
    return f"{first.meta.title} (+{n - 1})" if n > 1 else first.meta.title


def link(library: Library, ids: list[str], title: str | None = None) -> LinkedSet:
    with _locked(library):
        return _link(library, ids, title)


def _link(library: Library, ids: list[str], title: str | None = None) -> LinkedSet:
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
    recs.sort(key=_order)
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
    _refresh_title(library, target)
    return target


def move(library: Library, sid: str, rid: str, index: int) -> LinkedSet:
    with _locked(library):
        return _move(library, sid, rid, index)


def _move(library: Library, sid: str, rid: str, index: int) -> LinkedSet:
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
    with _locked(library):
        _unlink(library, rid)


def _unlink(library: Library, rid: str) -> None:
    """Take one recording out of its set; a set left with one member is dissolved."""
    _take_out(library, {rid})


def dissolve(library: Library, sid: str) -> None:
    with _locked(library):
        _dissolve(library, sid)


def _dissolve(library: Library, sid: str) -> None:
    _delete(library, sid)


def rename(library: Library, sid: str, title: str) -> None:
    with _locked(library):
        _rename(library, sid, title)


def _rename(library: Library, sid: str, title: str) -> None:
    s = get(library, sid)
    if s is not None and title.strip():
        s.title, s.title_auto = title.strip(), False
        _save(library, s)


def refresh_title(library: Library, s: LinkedSet | None) -> None:
    with _locked(library):
        _refresh_title(library, s)


def _refresh_title(library: Library, s: LinkedSet | None) -> None:
    """A set not renamed takes its title from the first part's first sentence once there is text."""
    s = get(library, s.id) if s is not None else None  # as on disk now, not as read before the lock
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
    """Remove set files that claim no recording at all. Returns how many.

    A set whose members are all missing is kept: they may be in the trash or not synced yet,
    and coming back they rejoin it (the index lists no set with fewer than two present).
    """
    n = 0
    with _locked(library):
        for s in load_all(library):
            if not s.claimed:
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


# ---- bursts: voice notes that look like one conversation -------------------------------------------
# WhatsApp caps a voice note's length, so a long message arrives as several notes. Desktop exports
# name each note with its time ("WhatsApp Ptt 2026-10-23 at 14.02.11"): a note starting within
# BURST_GAP_S of the previous one's end continues it. Android exports name them by date and a
# running number per chat export ("PTT-20261023-WA0004"): the next number, or up to two numbers
# further (a photo or a file sent in between takes a number too), continues it.
BURST_GAP_S = 600
BURST_NUMBER_GAP = 3


@dataclass
class Offer:
    ids: list[str]  # the recordings to link (or to add), in order
    set_id: str | None = None  # add them to this set instead of making a new one
    set_title: str = ""

    @property
    def key(self) -> str:
        """Identifies the offer for remembering a dismissal."""
        return ",".join(sorted(self.ids)) + (f">{self.set_id}" if self.set_id else "")


def whatsapp_key(rec: Recording) -> tuple[str, str, float] | None:
    """("desktop", day, start seconds) or ("android", day, note number) from the original file name."""
    from .importer import _WA_ANDROID, _WA_DESKTOP

    if rec.meta.origin != "imported" or not rec.meta.source:
        return None
    stem = Path(rec.meta.source).stem
    m = _WA_ANDROID.match(stem)
    if m:
        return "android", m["d"], float(m["n"])
    if _WA_DESKTOP.match(stem):
        try:
            when = datetime.fromisoformat(rec.meta.created)
        except ValueError:
            return None
        return "desktop", when.strftime("%Y%m%d"), when.timestamp()
    return None


def _runs(recs: list[Recording]) -> list[list[Recording]]:
    keyed = [(whatsapp_key(r), r) for r in recs]
    keyed = [(k, r) for k, r in keyed if k is not None]
    runs: list[list[Recording]] = []
    for kind in ("android", "desktop"):
        items = sorted(((k, r) for k, r in keyed if k[0] == kind), key=lambda x: (x[0][1], x[0][2], x[1].id))
        run: list[Recording] = []
        last = None
        for k, r in items:
            if last is not None:
                lk, lr = last
                if kind == "android":
                    joined = k[1] == lk[1] and 0 < k[2] - lk[2] <= BURST_NUMBER_GAP
                else:
                    joined = k[2] - (lk[2] + (lr.meta.duration or 0)) <= BURST_GAP_S
                if not joined:
                    runs.append(run)
                    run = []
            run.append(r)
            last = (k, r)
        runs.append(run)
    return [r for r in runs if len(r) >= 2]


def bursts(library: Library, new_ids, recordings: list[Recording] | None = None) -> list[Offer]:
    """Offers to link voice notes that look like one burst, for recordings just imported.

    The pool is the new recordings and the library's recordings from the same days. A run of
    notes none of which is linked becomes an offer for a new set; a run whose linked notes all
    belong to one set offers to add the new ones to it. Nothing is linked here.
    """
    new = set(new_ids)
    recs = library.all() if recordings is None else recordings
    days = {r.meta.created[:10] for r in recs if r.id in new}
    pool = [r for r in recs if r.meta.created[:10] in days]
    all_sets = load_all(library)
    member_of = membership(all_sets)
    titles = {st.id: st.title for st in all_sets}
    offers = []
    for run in _runs(pool):
        if not any(r.id in new for r in run):
            continue
        in_sets = {member_of[r.id] for r in run if r.id in member_of}
        free = [r.id for r in run if r.id not in member_of]
        if not in_sets and len(free) >= 2:
            offers.append(Offer(free))
        elif len(in_sets) == 1 and any(i in new for i in free):
            sid = in_sets.pop()
            offers.append(Offer(free, sid, titles.get(sid, "")))
    return offers

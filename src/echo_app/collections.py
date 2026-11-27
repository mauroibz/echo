"""Collections: recordings filed apart from the day-to-day list (stdlib only).

A batch dropped in together (a round of interviews, a course, a client's archive) is filed under a
name and shown only when that collection is opened, so the list stays the day's work however much
is imported. A recording is in one collection or in none, and the name is a field of its
meta.json: there is no file for a collection, so one exists while a recording names it and
nothing can point at a collection that is not there. Names compare without case or accents, as
tags do; the spelling shown is the one most of its recordings carry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .fsutil import atomic_write_json, read_json
from .library import T_DONE, Library, Recording, fold_tag

NAME_MAX = 60
LOOKS = "collections.json"  # in the data folder: {"icons": {folded name: icon}}
# An icon is a symbol and optionally a color, "hospital" or "hospital:coral". The symbols are among
# the window's bundled ones and the colors are theme roles that read on the sidebar; both are
# offered in this order, eight to a row. Not emoji: the Qt that Echo ships with draws color emoji
# fonts as nothing (measured on Fedora 44 with Noto Color Emoji, Qt 6.12), and a symbol in the
# theme's colors needs no font at all.
ICONS = ("star", "heart", "flag", "bookmark", "target", "flame", "lightbulb", "rocket",
         "briefcase", "building-2", "landmark", "factory", "house", "school", "graduation-cap", "book-open",
         "hospital", "stethoscope", "ambulance", "brain", "flask-conical", "scale", "shield", "lock",
         "users", "handshake", "phone", "video", "mic", "headphones", "presentation", "message-square-text",
         "chart-column", "banknote", "wrench", "truck", "plane", "globe", "calendar", "coffee")
COLORS = ("", "foam", "coral", "amber", "lilac", "lime")  # "": the color of the text around it
_ICON = re.compile(r"^[a-z0-9-]{1,40}(:[a-z_]{1,20})?$")


def clean(name: str) -> str:
    """A name as stored: one line, up to NAME_MAX characters; "" if nothing is left."""
    return " ".join(str(name or "").split())[:NAME_MAX].strip()


def same(a: str, b: str) -> bool:
    return fold_tag(clean(a)) == fold_tag(clean(b))


def clean_icon(icon: str) -> str:
    """An icon as stored, "symbol" or "symbol:color"; "" for none or for anything else."""
    icon = str(icon or "").strip().lower()
    return icon if _ICON.match(icon) else ""


def icon_parts(icon: str) -> tuple[str, str]:
    """("hospital", "coral") from "hospital:coral"; the color is "" when none or not one of COLORS."""
    name, _sep, color = clean_icon(icon).partition(":")
    return name, color if color in COLORS else ""


def icons(lib: Library) -> dict[str, str]:
    """Each collection's icon, by folded name. The file holds only looks: which recordings a
    collection has is in the recordings, so losing this file loses icons and nothing else."""
    try:
        d = read_json(lib.data_dir / LOOKS)
    except (OSError, ValueError):
        return {}
    found = d.get("icons") if isinstance(d, dict) else None
    return {str(k): clean_icon(v) for k, v in found.items() if clean_icon(v)} if isinstance(found, dict) else {}


def set_icon(lib: Library, name: str, icon: str) -> None:
    """Give a collection an icon ("" removes it)."""
    found = icons(lib)
    key, icon = fold_tag(clean(name)), clean_icon(icon)
    if icon:
        found[key] = icon
    else:
        found.pop(key, None)
    atomic_write_json(lib.data_dir / LOOKS, {"icons": found}, mkdir=True)


@dataclass
class Collection:
    name: str
    recordings: list[Recording]  # newest first
    icon: str = ""

    @property
    def transcribed(self) -> int:
        return sum(1 for r in self.recordings if r.transcript_status() == T_DONE)


def group(recs, looks: dict[str, str] | None = None) -> list[Collection]:
    """The collections among `recs`, by name; `looks` gives their icons (see `icons`)."""
    by: dict[str, list[Recording]] = {}
    for rec in recs:
        if clean(rec.meta.collection):
            by.setdefault(fold_tag(clean(rec.meta.collection)), []).append(rec)
    out = []
    for key, members in by.items():
        spellings = [clean(r.meta.collection) for r in members]
        name = max(sorted(set(spellings)), key=spellings.count)
        out.append(Collection(name, sorted(members, key=lambda r: r.meta.created, reverse=True),
                              (looks or {}).get(key, "")))
    return sorted(out, key=lambda c: fold_tag(c.name))


def all_of(lib: Library) -> list[Collection]:
    return group(lib.all(), icons(lib))


def get(lib: Library, name: str) -> Collection | None:
    return next((c for c in all_of(lib) if same(c.name, name)), None)


def spelling(lib: Library, name: str) -> str:
    """`name` as the collection it means is already spelled, else cleaned."""
    c = get(lib, name)
    return c.name if c is not None else clean(name)


def apart(rec: Recording) -> bool:
    """Whether a recording is a batch filed away from the day's work: in a collection, and brought
    in from files. One the user recorded is their day's work wherever they chose to file it, so
    what looks at the day to day (an extension's briefing, its calendar) still counts it."""
    return bool(clean(rec.meta.collection)) and rec.meta.origin != "recorded"


def for_new(lib: Library) -> str:
    """The collection a new recording goes to: the one chosen under Record, as it is spelled
    among the recordings; "" for the day-to-day list."""
    from . import settings

    name = clean(settings.load()[0].record_collection)
    return spelling(lib, name) if name else ""


def set_for_new(name: str) -> str:
    """Remember where new recordings go ("": the day-to-day list). Returns the name kept."""
    from . import settings

    cfg, _ = settings.load()
    cfg.record_collection = clean(name)
    settings.save(cfg)
    return cfg.record_collection


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
    if c.icon and not same(old, new):  # the icon goes with it, unless the one it joins has its own
        if not icons(lib).get(fold_tag(new)):
            set_icon(lib, new, c.icon)
        set_icon(lib, old, "")
    return len(c.recordings)


def dissolve(lib: Library, name: str) -> int:
    """Back to the day-to-day list, every recording of it; nothing is deleted."""
    c = get(lib, name)
    if c is None:
        return 0
    if c.icon:
        set_icon(lib, name, "")
    return file(c.recordings, "")

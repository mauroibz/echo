"""Studio's results as JSON-ready dicts, for `echo-app meetings`, `minutes` and `actions` (stdlib only).

This is how minutes and action items leave Echo: a script, a cron sync or an agent reads these
commands and loads the items into the team's tracker. Like `echo_app.cli_json`, keys are only
ever added, never renamed or removed.
"""

from __future__ import annotations

import re
from datetime import datetime

from echo_app import export
from echo_app.cli_json import record
from echo_app.library import Recording

from . import actions, marks, summary

QUOTE_BEFORE, QUOTE_AFTER = 5.0, 25.0  # seconds of transcript around an item's time, for its quote


def quote(rec: Recording, at: float | None) -> str:
    """What was said around `at`: the passages from a few seconds before to about half a minute after,
    with the speakers' names, so whoever reads the item sees the words it came from."""
    if at is None:
        return ""
    out, last = [], None
    for start, end, text, _p, who in export.cues(rec):
        if end < at - QUOTE_BEFORE or start > at + QUOTE_AFTER:
            continue
        name = export.speaker_name(rec, who)
        out.append(f"{name}: {text}" if name and name != last else text)
        last = name
    return " ".join(out)


def _email_of(lib, name: str) -> str | None:
    if lib is None or not name:
        return None
    from echo_app import people

    return people.load(lib, name).email or None


def action_dict(rec: Recording, it: dict, index: int, lib=None) -> dict:
    return {"index": index, "text": it["text"], "description": it["description"], "owner": it["owner"],
            "owner_email": _email_of(lib, it["owner"]),
            "due": it["due"] or None,
            "at": it["at"], "at_stamp": export.stamp(it["at"]) if it["at"] is not None else None,
            "context": it["context"], "note": it["note"], "edited": it["edited"], "added_by_user": it["origin"] == "user",
            "quote": quote(rec, it["at"]), "recording": rec.id}


def action_items(rec: Recording, discarded: bool = False, lib=None) -> list[dict]:
    items = (actions.load(rec) or {}).get("items", [])
    return [action_dict(rec, it, k, lib) for k, it in enumerate(items) if discarded or not it["discarded"]]


def meeting(rec: Recording, full: bool = True, lib=None) -> dict:
    """The recording (as `echo-app info --json`) with its minutes: the summary and the action items.
    `full=False` leaves out the summary's text and the items, for a list."""
    d = record(rec)
    data = summary.load(rec)
    items = action_items(rec, lib=lib)
    d["minutes"] = None if data is None else {
        "path": str(rec.path(summary.FILE).resolve()), "created": data.get("created"),
        "stale": summary.stale(rec, data), "template": data.get("template"),
        "excerpt": excerpt(data["text"]), **({"text": data["text"]} if full else {})}
    d["action_items"] = items if full else len(items)
    d["starred"] = marks.starred(rec)
    from . import calendar

    ev = calendar.event_of(rec)
    d["event"] = None if ev is None else {k: v for k, v in ev.as_dict().items() if k != "attendees"}
    d["attendees"] = [] if ev is None else [
        {**a, "person": _person_of(lib, a["email"])} for a in ev.as_dict()["attendees"]]
    return d


def _person_of(lib, email: str) -> str | None:
    if lib is None:
        return None
    from echo_app import people

    p = people.by_email(lib, email)
    return p.name if p is not None else None


def excerpt(text: str, limit: int = 280) -> str:
    """A line or two to show for the minutes: the first section's prose or bullets (summaries are
    mostly headings and lists), joined as sentences and cut at a word. The next steps, a later
    section, are left to the action items."""
    def clean(t: str) -> str:
        t = " ".join(re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", t).replace("**", "").split())
        return t if not t or t[-1] in ".!?…:" else t + "."

    out = ""
    for ln in text.splitlines():
        if not ln.strip() or ln.lstrip().startswith("|"):
            continue
        if ln.lstrip().startswith("#"):
            if out:
                break  # the first section is enough
            continue
        nxt = f"{out} {clean(ln)}".strip()
        if out and len(nxt) > limit:
            break
        out = nxt
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + "…"


def in_range(rec: Recording, since: str | None, until: str | None) -> bool:
    """Whether the recording was made on or after `since` and before the end of `until` (dates or
    times in ISO; compared as local times)."""
    try:
        when = datetime.fromisoformat(rec.meta.created)
    except ValueError:
        return False
    when = when.replace(tzinfo=None)
    if since and when < _day(since, end=False):
        return False
    return not (until and when >= _day(until, end=True))


def _day(s: str, end: bool) -> datetime:
    from datetime import date, timedelta

    s = s.strip()
    if s in ("today", "yesterday"):
        d = date.today() - timedelta(days=0 if s == "today" else 1)
        dt = datetime(d.year, d.month, d.day)
    else:
        dt = datetime.fromisoformat(s).replace(tzinfo=None)
        if len(s) > 10:
            return dt
    return dt + timedelta(days=1) if end else dt

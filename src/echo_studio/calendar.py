"""The user's calendar, read from private ICS addresses: the next meetings, and the event a
recording belongs to (stdlib only).

Google Calendar ("Secret address in iCal format") and Outlook/Teams ("Publish a calendar", ICS)
give an address that anyone holding it can read, so the addresses are kept in the keyring like
the API key, never in a file; `$ECHO_CALENDAR_URLS` (one per line or separated by spaces) wins
over it. Studio only reads them: it never writes to a calendar. The last copy of each feed is
kept in the cache folder so the home and the matching work offline.

A recording's event is saved in its folder as `event.json` (its title, times, description, video
link and attendees with their emails), so what the recording was stays with it when the
calendar changes or is gone; the index and the window only read it.
"""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from echo_app import paths, people
from echo_app.fsutil import atomic_write_json, atomic_write_text, read_json
from echo_app.library import Recording, fold_tag

from . import ics, keychain

log = logging.getLogger(__name__)

URLS_ENV = "ECHO_CALENDAR_URLS"
KEY = "calendar"  # the keyring entry's "server" attribute
EVENT_FILE = "event.json"
FETCH_TIMEOUT_S = 20
REFRESH_MINUTES = 10
EARLY_S = 10 * 60  # a recording started up to this long before an event is that event's
AFTER_END_S = 10 * 60  # ... or up to this long after its end, the meeting having run late

_urls: list[str] | None = None


def urls() -> list[str]:
    """The calendar addresses: the environment's, else the keyring's (read once)."""
    global _urls
    if os.environ.get(URLS_ENV):
        return _clean(os.environ[URLS_ENV])
    if _urls is None:
        _urls = _clean(keychain.lookup(KEY))
    return _urls


def _clean(text: str) -> list[str]:
    out = []
    for u in text.split():
        u = u.strip()
        if u.startswith("webcal://"):
            u = "https://" + u[len("webcal://"):]
        if u.startswith(("https://", "http://")) and u not in out:
            out.append(u)
    return out


def save_urls(text: str) -> list[str]:
    """Keep the addresses in `text` in the keyring (none: forget them). Raises KeychainError."""
    global _urls
    found = _clean(text)
    if found == urls() and not os.environ.get(URLS_ENV):
        return found
    if found:
        keychain.store(KEY, "\n".join(found), label="Echo Studio calendar addresses")
    else:
        keychain.clear(KEY)
    _urls = found
    for p in _cache_dir().glob("*.ics") if _cache_dir().exists() else []:
        if p.stem not in {_name(u) for u in found}:
            p.unlink(missing_ok=True)  # a calendar taken out goes from the cache too
    return found


def enabled() -> bool:
    return bool(urls())


def _cache_dir():
    return paths.cache_dir() / "studio" / "calendar"


def _name(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Echo Studio", "Accept": "text/calendar"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as r:  # noqa: S310 - the user's own address
            data = r.read()
    except urllib.error.HTTPError as e:
        raise OSError(f"the calendar answered {e.code}" + (" (the address may have been reset)"
                                                            if e.code in (401, 403, 404) else "")) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise OSError(f"could not reach the calendar: {getattr(e, 'reason', e)}") from None
    text = data.decode("utf-8", "replace")
    if "BEGIN:VCALENDAR" not in text[:2000]:
        raise OSError("that address does not give a calendar (ICS)")
    return text


def refresh() -> list[str]:
    """Fetch every calendar into the cache; returns the errors, one per calendar that failed."""
    errors = []
    for u in urls():
        try:
            text = fetch(u)
        except OSError as e:
            errors.append(f"{_host(u)}: {e}")
            continue
        atomic_write_text(_cache_dir() / f"{_name(u)}.ics", text, mkdir=True)
    return errors


def _host(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).hostname or url


def _texts() -> list[str]:
    out = []
    for u in urls():
        try:
            out.append((_cache_dir() / f"{_name(u)}.ics").read_text(encoding="utf-8"))
        except OSError:
            pass
    return out


def events(since: datetime, until: datetime) -> list[ics.Event]:
    """Events from every calendar overlapping [since, until], by start; the same event in two
    calendars (an invitation in both) once."""
    seen, out = set(), []
    for text in _texts():
        try:
            evs = ics.parse(text, since, until)
        except (ValueError, KeyError, IndexError) as e:
            log.warning("calendar not read: %s", e)
            continue
        for e in evs:
            k = (e.uid, e.start)
            if k not in seen:
                seen.add(k)
                out.append(e)
    return sorted(out, key=lambda e: (e.start, e.title))


def upcoming(now: datetime | None = None, hours: float = 24) -> list[ics.Event]:
    """Meetings (not whole-day events) that have not ended, in the next `hours`."""
    now = now or datetime.now().astimezone()
    return [e for e in events(now, now + timedelta(hours=hours)) if not e.all_day and e.end > now]


# ---- a recording's event ----

def event_of(rec: Recording) -> ics.Event | None:
    try:
        return ics.Event.from_dict(read_json(rec.path(EVENT_FILE)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def match(rec: Recording) -> ics.Event | None:
    """The event the recording was made in: one that had started (or was about to, up to
    EARLY_S) when the recording started and had not ended long before; the latest started wins
    (a meeting that follows another)."""
    try:
        start = datetime.fromisoformat(rec.meta.created)
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.astimezone()
    cands = [e for e in events(start - timedelta(hours=12), start + timedelta(hours=1)) if not e.all_day
             and e.start - timedelta(seconds=EARLY_S) <= start <= e.end + timedelta(seconds=AFTER_END_S)
             and start <= e.end]  # a recording started after the meeting ended is something else
    return max(cands, key=lambda e: e.start) if cands else None


def attach(rec: Recording, event: ics.Event) -> None:
    """Keep the event with the recording; name an unnamed recording after it, and give
    transcription the attendees' names as context when the recording has none yet."""
    atomic_write_json(rec.path(EVENT_FILE), event.as_dict())
    changes = {}
    if rec.meta.title_auto or not rec.meta.title.strip():
        changes.update(title=event.title, title_auto=False)
    names = [a.name for a in event.attendees if a.name]
    if names and not rec.meta.context_line.strip() and rec.transcript() is None:
        changes["context_line"] = f"{event.title}, with {', '.join(names)}"[:300]
    if changes:
        rec.update(**changes)


def attach_if_found(rec: Recording) -> ics.Event | None:
    """The recording's event, saved with it when found in the calendar; None when there is none."""
    ev = event_of(rec)
    if ev is None and enabled():
        ev = match(rec)
        if ev is not None:
            attach(rec, ev)
    return ev


def attendee_names(lib, rec: Recording) -> list[str]:
    """The names to offer when naming the recording's speakers: its event's attendees, as the
    People know them (by email) or as the calendar names them."""
    ev = event_of(rec)
    if ev is None:
        return []
    out = []
    for a in ev.attendees:
        prof = people.by_email(lib, a.email)
        name = prof.name if prof is not None else a.name
        if name and name not in out:
            out.append(name)
    return out


def learn_emails(lib, rec: Recording) -> list[str]:
    """Give the people named in the recording the email of the attendee with their name, when they
    have none and nobody else has it: the calendar teaches Echo who is who. Returns who learned one."""
    ev = event_of(rec)
    if ev is None:
        return []
    by_name: dict[str, list[ics.Attendee]] = {}
    for a in ev.attendees:
        if a.name:
            by_name.setdefault(fold_tag(a.name), []).append(a)
            first = fold_tag(a.name.split()[0])
            by_name.setdefault("first:" + first, []).append(a)
    learned = []
    for name in dict.fromkeys(n for n in rec.meta.speakers.values() if n):
        hits = by_name.get(fold_tag(name)) or (by_name.get("first:" + fold_tag(name)) if " " not in name else None)
        if not hits or len(hits) != 1:
            continue  # no attendee by that name, or two Carlas
        email = hits[0].email
        prof = people.load(lib, name)
        if prof.email or people.by_email(lib, email) is not None:
            continue
        prof.email = email
        people.save(lib, prof)
        learned.append(name)
    return learned

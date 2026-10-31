"""A small iCalendar (RFC 5545) reader for the events in a published calendar (stdlib only).

Google Calendar's and Outlook's "secret address" feeds are what Studio reads, so this covers what
they write: VEVENTs with times in UTC, with a TZID (an IANA name, or a Windows name that comes
with its VTIMEZONE), or whole days; recurring events (RRULE with FREQ, INTERVAL, COUNT, UNTIL,
BYDAY, BYMONTHDAY, BYMONTH), their EXDATEs and the occurrences moved or cancelled through
RECURRENCE-ID; and the attendees with their emails. No dependency does this within Echo's
lean rule (icalendar plus recurring-ical-events would be two packages and their own pins).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_OCCURRENCES = 2000  # per recurring event, whatever its rule says: a daily event for years

DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
LINK = re.compile(r"https://(?:[\w-]+\.)*(?:meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|zoom\.us|"
                  r"whereby\.com|webex\.com|meet\.jit\.si)/[^\s<>\"'\\]+", re.I)


@dataclass
class Attendee:
    email: str
    name: str = ""
    status: str = ""  # ACCEPTED, DECLINED, TENTATIVE, NEEDS-ACTION


@dataclass
class Event:
    uid: str
    title: str
    start: datetime  # aware; a whole day starts at local midnight
    end: datetime
    all_day: bool = False
    description: str = ""
    location: str = ""
    link: str = ""  # the video call's address, when there is one
    attendees: list[Attendee] = field(default_factory=list)
    organizer: str = ""

    def as_dict(self) -> dict:
        return {"uid": self.uid, "title": self.title, "start": self.start.isoformat(), "end": self.end.isoformat(),
                "all_day": self.all_day, "description": self.description, "location": self.location,
                "link": self.link, "organizer": self.organizer,
                "attendees": [{"email": a.email, "name": a.name, "status": a.status} for a in self.attendees]}

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        return cls(str(d.get("uid") or ""), str(d.get("title") or ""), datetime.fromisoformat(d["start"]),
                   datetime.fromisoformat(d["end"]), bool(d.get("all_day")), str(d.get("description") or ""),
                   str(d.get("location") or ""), str(d.get("link") or ""),
                   [Attendee(str(a.get("email") or ""), str(a.get("name") or ""), str(a.get("status") or ""))
                    for a in d.get("attendees") or []], str(d.get("organizer") or ""))


# ---- lines and properties ----

def _unfold(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def _split(line: str) -> tuple[str, dict[str, str], str]:
    """NAME;PARAM=value;...:VALUE, with quoted parameter values (which may hold ':' and ';')."""
    i, quoted = 0, False
    while i < len(line):
        c = line[i]
        if c == '"':
            quoted = not quoted
        elif c == ":" and not quoted:
            break
        i += 1
    head, value = line[:i], line[i + 1:]
    parts = re.findall(r'(?:[^;"]|"[^"]*")+', head)
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return (parts[0].upper() if parts else ""), params, value


def _text(v: str) -> str:
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v).strip()


# ---- times ----

def _offset(s: str) -> timezone:
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    return timezone(sign * timedelta(hours=int(s[:2]), minutes=int(s[2:4] or 0)))


class _Zones:
    """TZIDs to tzinfo: IANA names through zoneinfo; others (Outlook's Windows names) through the
    VTIMEZONE in the file, by its standard offset, else the local zone."""

    def __init__(self, vtimezones: dict[str, str]):
        self.fixed = vtimezones
        self.cache: dict[str, tzinfo] = {}

    def get(self, tzid: str | None) -> tzinfo | None:
        if not tzid:
            return None
        if tzid not in self.cache:
            try:
                self.cache[tzid] = ZoneInfo(tzid)
            except (ZoneInfoNotFoundError, ValueError):
                off = self.fixed.get(tzid)
                self.cache[tzid] = _offset(off) if off else datetime.now().astimezone().tzinfo
        return self.cache[tzid]


def _time(value: str, params: dict, zones: _Zones) -> tuple[datetime, bool]:
    """(aware datetime, whole day)."""
    v = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", v):
        d = datetime.strptime(v[:8], "%Y%m%d")
        return d.astimezone(), True  # local midnight
    dt = datetime.strptime(v.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if v.endswith("Z"):
        return dt.replace(tzinfo=timezone.utc), False
    tz = zones.get(params.get("TZID"))
    return (dt.replace(tzinfo=tz) if tz else dt.astimezone()), False


# ---- recurrence ----

def _rule(s: str) -> dict[str, str]:
    return {k.upper(): v for k, _, v in (p.partition("=") for p in s.split(";") if p)}


def _byday(rule: dict) -> list[tuple[int, int]]:
    """[(nth or 0, weekday 0-6)]: "2TU" is the second Tuesday, "-1FR" the last Friday."""
    out = []
    for d in filter(None, rule.get("BYDAY", "").split(",")):
        m = re.fullmatch(r"([+-]?\d+)?([A-Z]{2})", d.strip().upper())
        if m and m.group(2) in DAYS:
            out.append((int(m.group(1) or 0), DAYS.index(m.group(2))))
    return out


def _nth_weekday(year: int, month: int, nth: int, wd: int) -> date | None:
    first = date(year, month, 1)
    days = [first + timedelta(days=i) for i in range(31) if (first + timedelta(days=i)).month == month]
    hits = [d for d in days if d.weekday() == wd]
    try:
        return hits[nth - 1] if nth > 0 else hits[nth]
    except IndexError:
        return None


def occurrences(start: datetime, rrule: str, until: datetime) -> list[datetime]:
    """The starts of a recurring event up to `until` (aware), the first included. Wall-clock times
    stay the same across daylight-saving changes, as calendars mean them."""
    r = _rule(rrule)
    freq = r.get("FREQ", "")
    step = max(1, int(r.get("INTERVAL", "1") or 1))
    count = int(r["COUNT"]) if r.get("COUNT", "").isdigit() else None
    end = until
    if r.get("UNTIL"):
        u = r["UNTIL"]
        try:
            ue = (datetime.strptime(u[:8], "%Y%m%d").replace(hour=23, minute=59, second=59) if len(u) == 8 else
                  datetime.strptime(u.rstrip("Z")[:15], "%Y%m%dT%H%M%S"))
            ue = ue.replace(tzinfo=timezone.utc) if u.endswith("Z") else ue.replace(tzinfo=start.tzinfo)
            end = min(end, ue)
        except ValueError:
            pass
    days = _byday(r)
    monthdays = [int(x) for x in r.get("BYMONTHDAY", "").split(",") if x.lstrip("-").isdigit()]
    months = [int(x) for x in r.get("BYMONTH", "").split(",") if x.isdigit()]
    wall = start.replace(tzinfo=None)
    tz = start.tzinfo
    out: list[datetime] = []

    def emit(d: date) -> bool:
        """Add the occurrence on day `d`; False once past the end or the count."""
        when = datetime.combine(d, wall.time()).replace(tzinfo=tz)
        if when < start:
            return True
        if when > end or (count is not None and len(out) >= count) or len(out) >= MAX_OCCURRENCES:
            return False
        out.append(when)
        return True

    d0 = wall.date()
    if freq == "DAILY":
        d = d0
        while emit(d):
            d += timedelta(days=step)
    elif freq == "WEEKLY":
        wds = sorted({wd for _n, wd in days}) or [d0.weekday()]
        week = d0 - timedelta(days=d0.weekday())
        while True:
            for wd in wds:
                if not emit(week + timedelta(days=wd)):
                    return out
            week += timedelta(weeks=step)
    elif freq in ("MONTHLY", "YEARLY"):
        y, m = d0.year, d0.month
        while True:
            for mo in (months or [m]) if freq == "YEARLY" else [m]:
                cands: list[date] = []
                if days:
                    cands = [x for n, wd in days for x in ([_nth_weekday(y, mo, n, wd)] if n else
                             [dd for dd in (date(y, mo, 1) + timedelta(days=i) for i in range(31))
                              if dd.month == mo and dd.weekday() == wd]) if x]
                elif monthdays:
                    for md in monthdays:
                        try:
                            last = (date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)).day
                            cands.append(date(y, mo, md if md > 0 else last + md + 1))
                        except ValueError:
                            pass
                else:
                    try:
                        cands = [date(y, mo, d0.day)]
                    except ValueError:
                        cands = []  # the 31st in a shorter month: none, as RFC 5545 says
                for c in sorted(cands):
                    if not emit(c):
                        return out
            if freq == "MONTHLY":
                m += step
                y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            else:
                y += step
            if datetime(y, m if freq == "MONTHLY" else 1, 1, tzinfo=tz) > end:
                return out
    else:
        emit(d0)
    return out


# ---- the calendar ----

def _components(lines: list[str], name: str) -> list[list[str]]:
    out, cur, depth = [], None, 0
    for ln in lines:
        if ln.upper() == f"BEGIN:{name}":
            cur, depth = [], 0
            continue
        if cur is None:
            continue
        if ln.upper().startswith("BEGIN:"):
            depth += 1
        elif ln.upper() == f"END:{name}" and depth == 0:
            out.append(cur)
            cur = None
            continue
        elif ln.upper().startswith("END:"):
            depth -= 1
        if depth == 0:
            cur.append(ln)
    return out


def parse(text: str, since: datetime, until: datetime) -> list[Event]:
    """The events that overlap [since, until], recurring ones expanded, sorted by start. Cancelled
    events and occurrences are left out."""
    lines = _unfold(text)
    zones = _Zones(_std_offsets(text))
    masters: dict[str, dict] = {}
    overrides: dict[tuple[str, str], dict] = {}
    for comp in _components(lines, "VEVENT"):
        props: dict[str, list[tuple[dict, str]]] = {}
        for ln in comp:
            name, params, value = _split(ln)
            props.setdefault(name, []).append((params, value))
        uid = props.get("UID", [({}, "")])[0][1]
        if "RECURRENCE-ID" in props:
            p, v = props["RECURRENCE-ID"][0]
            overrides[(uid, _key(_time(v, p, zones)[0]))] = props
        else:
            masters[uid or f"noid-{len(masters)}"] = props
    events = []
    for uid, props in masters.items():
        if not props.get("DTSTART"):
            continue
        start, all_day = _time(props["DTSTART"][0][1], props["DTSTART"][0][0], zones)
        if props.get("DTEND"):
            end = _time(props["DTEND"][0][1], props["DTEND"][0][0], zones)[0]
        elif props.get("DURATION"):
            end = start + _duration(props["DURATION"][0][1])
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(0))
        length = end - start
        if props.get("RRULE"):
            starts = occurrences(start, props["RRULE"][0][1], until)
            ex = {_key(_time(x, p, zones)[0]) for p, v in props.get("EXDATE", []) for x in v.split(",") if x}
            starts = [s for s in starts if _key(s) not in ex]
        else:
            starts = [start]
        for s in starts:
            o = overrides.pop((uid, _key(s)), None)
            src = {**props, **o} if o else props  # a moved occurrence keeps what it does not restate
            if _status(src) == "CANCELLED":
                continue
            if o is not None and o.get("DTSTART"):
                s2 = _time(o["DTSTART"][0][1], o["DTSTART"][0][0], zones)[0]
                e2 = _time(o["DTEND"][0][1], o["DTEND"][0][0], zones)[0] if o.get("DTEND") else s2 + length
            else:
                s2, e2 = s, s + length
            if e2 >= since and s2 <= until:
                events.append(_event(uid, src, s2, e2, all_day))
    for (uid, _k), props in overrides.items():  # a moved occurrence whose rule did not reach here
        if props.get("DTSTART") and _status(props) != "CANCELLED" and uid in masters:
            s = _time(props["DTSTART"][0][1], props["DTSTART"][0][0], zones)[0]
            e = _time(props["DTEND"][0][1], props["DTEND"][0][0], zones)[0] if props.get("DTEND") else s
            if e >= since and s <= until:
                events.append(_event(uid, props, s, e, False))
    return sorted(events, key=lambda e: (e.start, e.title))


def _std_offsets(text: str) -> dict[str, str]:
    """TZID -> the STANDARD part's TZOFFSETTO, from each VTIMEZONE."""
    out = {}
    for block in re.findall(r"BEGIN:VTIMEZONE(.*?)END:VTIMEZONE", text, re.S):
        tzid = re.search(r"^TZID[^:]*:(.+)$", block, re.M)
        std = re.search(r"BEGIN:STANDARD(.*?)END:STANDARD", block, re.S)
        off = re.search(r"TZOFFSETTO:([+-]\d{4})", std.group(1) if std else block)
        if tzid and off:
            out[tzid.group(1).strip()] = off.group(1)
    return out


def _key(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _status(props: dict) -> str:
    return props.get("STATUS", [({}, "")])[0][1].strip().upper()


def _duration(v: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v.strip())
    if not m:
        return timedelta(0)
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    td = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
    return -td if m.group(1) == "-" else td


def _email(v: str) -> str:
    m = re.search(r"[^\s:<>\"]+@[^\s:<>\"]+", v)
    return m.group(0).lower() if m else ""


def _name(cn: str) -> str:
    """An attendee's name as people say it: Outlook's "Méndez, Carla" becomes "Carla Méndez"; an
    address used as the name is no name."""
    cn = " ".join(cn.split())
    if "@" in cn:
        return ""
    last, sep, first = cn.partition(", ")
    return f"{first} {last}" if sep and first and "," not in first else cn


def _event(uid: str, props: dict, start: datetime, end: datetime, all_day: bool) -> Event:
    def one(name: str) -> str:
        return _text(props.get(name, [({}, "")])[0][1])

    description, location = one("DESCRIPTION"), one("LOCATION")
    link = ""
    for cand in (one("X-GOOGLE-CONFERENCE"), location, description, one("URL")):
        m = LINK.search(cand or "")
        if m:
            link = m.group(0).rstrip(".,;)>")
            break
    attendees = []
    for params, value in props.get("ATTENDEE", []):
        email = _email(value) or _email(params.get("EMAIL", ""))
        if email and params.get("CUTYPE", "INDIVIDUAL").upper() in ("INDIVIDUAL", ""):
            attendees.append(Attendee(email, _name(params.get("CN", "")), params.get("PARTSTAT", "").upper()))
    org = props.get("ORGANIZER", [({}, "")])[0]
    return Event(uid, one("SUMMARY") or "(no title)", start, end, all_day, description, location, link,
                 attendees, _email(org[1]))

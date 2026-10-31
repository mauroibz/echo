"""Echo Studio's calendar: the ICS reader, a recording's event, and meetings recorded when they start."""

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from echo_app import cli, people
from echo_app.library import Library
from echo_studio import calendar, config, ics, summary
from test_studio import _attach, keyring, server, studio  # noqa: F401 - fixtures
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures
from test_vault import _rec

ART = timezone(timedelta(hours=-3))

FEED = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VTIMEZONE\r
TZID:Argentina Standard Time\r
BEGIN:STANDARD\r
DTSTART:16010101T000000\r
TZOFFSETFROM:-0300\r
TZOFFSETTO:-0300\r
END:STANDARD\r
END:VTIMEZONE\r
BEGIN:VEVENT\r
UID:weekly1\r
SUMMARY:Product sync\r
DTSTART;TZID=America/Argentina/Buenos_Aires:20261005T110000\r
DTEND;TZID=America/Argentina/Buenos_Aires:20261005T114500\r
RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261231T235959Z\r
EXDATE;TZID=America/Argentina/Buenos_Aires:20261028T110000\r
DESCRIPTION:Agenda: pagos y onboarding\\nÚnete: https://meet.google.com/abc-defg-hij\\nO llamá al +1 234 5
 67 8900\r
ATTENDEE;CN="Méndez, Carla";PARTSTAT=ACCEPTED:mailto:Carla@acme.example\r
ATTENDEE;CN=Sofía Paz;PARTSTAT=ACCEPTED:mailto:sofia@ejemplo.com\r
ATTENDEE;CUTYPE=ROOM;CN=Sala 3:mailto:sala@acme.example\r
BEGIN:VALARM\r
DESCRIPTION:reminder\r
END:VALARM\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:weekly1\r
RECURRENCE-ID;TZID=America/Argentina/Buenos_Aires:20261102T110000\r
SUMMARY:Product sync (moved)\r
DTSTART;TZID=America/Argentina/Buenos_Aires:20261102T150000\r
DTEND;TZID=America/Argentina/Buenos_Aires:20261102T153000\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:out1\r
SUMMARY:Roadmap review\r
DTSTART;TZID=Argentina Standard Time:20261031T150000\r
DTEND;TZID=Argentina Standard Time:20261031T154500\r
LOCATION:Microsoft Teams Meeting\r
DESCRIPTION:Join: https://teams.microsoft.com/l/meetup-join/19%3ameeting_x\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:gone\r
SUMMARY:Cancelada\r
STATUS:CANCELLED\r
DTSTART:20261030T130000Z\r
DTEND:20261030T140000Z\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:monthly\r
SUMMARY:Directorio\r
DTSTART:20260908T120000Z\r
DURATION:PT2H\r
RRULE:FREQ=MONTHLY;BYDAY=2TU;COUNT=3\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:day1\r
SUMMARY:Feriado\r
DTSTART;VALUE=DATE:20261102\r
DTEND;VALUE=DATE:20261103\r
END:VEVENT\r
END:VCALENDAR\r
"""


def _parse(since, until):
    return ics.parse(FEED, since, until)


def test_ics_reads_what_google_and_outlook_write():
    evs = _parse(datetime(2026, 10, 26, tzinfo=ART), datetime(2026, 11, 5, tzinfo=ART))
    got = [(e.start.astimezone(ART).strftime("%m-%d %H:%M"), e.title, e.all_day) for e in evs]
    assert got == [("10-26 11:00", "Product sync", False),  # the 28th is an EXDATE
                   ("10-31 15:00", "Roadmap review", False),  # a Windows zone, through its VTIMEZONE
                   ("11-02 00:00", "Feriado", True),
                   ("11-02 15:00", "Product sync (moved)", False),  # moved through RECURRENCE-ID
                   ("11-04 11:00", "Product sync", False)]
    sync = evs[0]
    assert sync.end - sync.start == timedelta(minutes=45)
    assert sync.link == "https://meet.google.com/abc-defg-hij"
    assert [(a.name, a.email, a.status) for a in sync.attendees] == [
        ("Carla Méndez", "carla@acme.example", "ACCEPTED"), ("Sofía Paz", "sofia@ejemplo.com", "ACCEPTED")]
    assert "pagos y onboarding" in sync.description and "\n" in sync.description
    assert evs[1].link.startswith("https://teams.microsoft.com/l/meetup-join/")
    moved = evs[3]
    assert moved.end - moved.start == timedelta(minutes=30) and moved.attendees  # keeps the master's attendees
    board = [e.start.date().isoformat() for e in _parse(datetime(2026, 9, 1, tzinfo=ART),
                                                         datetime(2027, 3, 1, tzinfo=ART)) if e.title == "Directorio"]
    assert board == ["2026-09-08", "2026-10-13", "2026-11-10"]  # second Tuesdays, COUNT=3
    assert ics.Event.from_dict(json.loads(json.dumps(sync.as_dict()))) == sync


def test_ics_durations_and_bad_input():
    assert ics._duration("PT1H30M") == timedelta(minutes=90) and ics._duration("P1D") == timedelta(days=1)
    assert ics.parse("not a calendar", datetime(2026, 1, 1, tzinfo=ART), datetime(2027, 1, 1, tzinfo=ART)) == []
    daily = "BEGIN:VEVENT\nUID:d\nSUMMARY:x\nDTSTART:20200101T100000Z\nDTEND:20200101T101500Z\nRRULE:FREQ=DAILY\nEND:VEVENT"
    evs = ics.parse(daily, datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert evs == []  # past MAX_OCCURRENCES: an endless daily rule is cut, not expanded for ever
    near = daily.replace("20200101", "20261001")
    assert len(ics.parse(near, datetime(2026, 10, 1, tzinfo=timezone.utc),
                         datetime(2026, 10, 3, 23, tzinfo=timezone.utc))) == 3


class Feed:
    def __init__(self, text):
        self.text = text
        self.status = 200
        feed = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = feed.text.encode()
                self.send_response(feed.status)
                self.send_header("Content-Type", "text/calendar")
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/private-abc/basic.ics"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture
def feed(monkeypatch):
    f = Feed(FEED)
    monkeypatch.setattr(calendar, "_urls", None)
    yield f
    f.httpd.shutdown()


def _now_feed(start: datetime, minutes: int = 45, link: bool = True) -> str:
    """One meeting at `start`, for the tests that run against the clock."""
    fmt = "%Y%m%dT%H%M%SZ"
    s, e = start.astimezone(timezone.utc), (start + timedelta(minutes=minutes)).astimezone(timezone.utc)
    desc = "DESCRIPTION:https://meet.google.com/xyz-abcd-efg\r\n" if link else ""
    return ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:now1\r\nSUMMARY:Roadmap review\r\n"
            f"DTSTART:{s:{fmt}}\r\nDTEND:{e:{fmt}}\r\n{desc}"
            "ATTENDEE;CN=Carla Méndez:mailto:carla@acme.example\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


def test_addresses_live_in_the_keyring(feed, keyring, tmp_path):
    assert calendar.urls() == [] and not calendar.enabled()
    calendar.save_urls(f"webcal://example.com/a.ics\n{feed.url}\nnot-a-url")
    assert calendar.urls() == ["https://example.com/a.ics", feed.url]
    assert feed.url in keyring.read_text()  # in the (fake) keyring, nowhere else
    assert not list(tmp_path.rglob("studio.toml")) or feed.url not in next(tmp_path.rglob("studio.toml")).read_text()
    calendar._urls = None
    assert calendar.urls()[1] == feed.url  # read back from the keyring
    calendar.save_urls(feed.url)
    errors = calendar.refresh()
    assert errors == []
    evs = calendar.events(datetime(2026, 10, 31, tzinfo=ART), datetime(2026, 11, 1, tzinfo=ART))
    assert [e.title for e in evs] == ["Roadmap review"]
    feed.status = 404
    assert "reset" in calendar.refresh()[0]
    assert [e.title for e in calendar.events(datetime(2026, 10, 31, tzinfo=ART),
                                             datetime(2026, 11, 1, tzinfo=ART))] == ["Roadmap review"]  # the copy
    calendar.save_urls("")
    assert calendar.urls() == [] and calendar.events(datetime(2026, 10, 31, tzinfo=ART),
                                                     datetime(2026, 11, 1, tzinfo=ART)) == []


def test_a_recording_gets_its_event(feed, tmp_path):
    lib = Library(tmp_path / "data")
    calendar.save_urls(feed.url)
    calendar.refresh()
    rec = _rec(lib)
    rec.update(created="2026-10-26T11:03:00-03:00", title="Grabación", title_auto=True, speakers={"1": "Carla"})
    ev = calendar.attach_if_found(rec)
    assert ev.title == "Product sync" and rec.path(calendar.EVENT_FILE).exists()
    rec = lib.get(rec.id)
    assert rec.meta.title == "Product sync" and not rec.meta.title_auto
    assert calendar.learn_emails(lib, rec) == ["Carla"]  # only one Carla invited: she is carla@acme
    assert people.load(lib, "Carla").email == "carla@acme.example"
    assert calendar.attendee_names(lib, rec) == ["Carla", "Sofía Paz"]  # as People knows her now
    header = summary._header(rec)
    assert "Calendar event: Product sync" in header and "Carla Méndez <carla@acme.example>" in header
    assert "pagos y onboarding" in header and "meet.google" not in header and "234 5" not in header
    late = _rec(lib)
    late.update(created="2026-10-26T13:00:00-03:00")
    assert calendar.attach_if_found(late) is None  # after the meeting: not it


def test_minutes_json_has_the_event(feed, tmp_path, server, capsys, studio):
    from echo_app import settings

    s = settings.load()[0]
    s.data_dir = str(tmp_path / "data")
    settings.save(s)
    lib = Library(tmp_path / "data")
    calendar.save_urls(feed.url)
    calendar.refresh()
    rec = _rec(lib)
    rec.update(created="2026-10-26T11:03:00-03:00")
    calendar.attach_if_found(rec)
    people.save(lib, people.Profile("lucia", email="lucia@acme.example"))
    summary.finish(rec, summary.write(rec))
    capsys.readouterr()
    assert cli.main(["minutes", rec.id, "--json"]) == 0
    m = json.loads(capsys.readouterr().out)
    assert m["event"]["title"] == "Product sync" and m["event"]["link"].startswith("https://meet.google.com/")
    assert [a["email"] for a in m["attendees"]] == ["carla@acme.example", "sofia@ejemplo.com"]
    assert m["action_items"][0]["owner_email"] == "lucia@acme.example"
    assert cli.main(["calendar", "--days", "400"]) == 0
    out = capsys.readouterr().out
    assert "Roadmap review" in out and "[video]" in out


def test_meetings_are_recorded_when_they_start(window, lib, feed, studio, monkeypatch):
    import echo_studio
    from echo_studio import meetings

    monkeypatch.setattr(meetings, "_state_path", lambda: lib.data_dir / "meetings-state.json")
    now = datetime.now().astimezone().replace(microsecond=0)
    feed.text = _now_feed(now - timedelta(minutes=1))
    calendar.save_urls(feed.url)
    _attach(window)
    m = echo_studio._meetings
    # The calendar is read at start, and the meeting that began a minute ago starts recording.
    assert wait_until(lambda: window.recording_id() is not None, 10)
    ev = m.next_event()
    assert ev.title == "Roadmap review"
    rid = window.recording_id()
    assert wait_until(lambda: m.active is not None)
    rec = lib.get(rid)
    assert rec.meta.title == "Roadmap review" and calendar.event_of(rec).uid == "now1"
    assert not m.will_record(ev)  # started once
    pump(600)
    m.tick(ev.end + timedelta(minutes=5))
    assert window.recording_id() == rid  # still within the 10 minutes after the end
    m.tick(ev.end + timedelta(minutes=11))
    assert window.recording_id() is None and m.active is None
    assert wait_until(lambda: lib.get(rid).meta.state == "ready", 20)
    m.tick(now)
    pump(300)
    assert window.recording_id() is None  # not started again


def test_skip_and_manual_recordings(window, lib, feed, studio, monkeypatch):
    import echo_studio
    from echo_studio import meetings

    monkeypatch.setattr(meetings, "_state_path", lambda: lib.data_dir / "meetings-state.json")
    now = datetime.now().astimezone().replace(microsecond=0)
    feed.text = _now_feed(now + timedelta(minutes=2))  # in two minutes
    calendar.save_urls(feed.url)
    _attach(window)
    m = echo_studio._meetings
    assert wait_until(lambda: m.next_event() is not None, 5)
    ev = m.next_event()
    assert m.will_record(ev) and window.recording_id() is None
    m.skip(ev)
    assert m.is_skipped(ev) and not m.will_record(ev)
    m.tick(ev.start + timedelta(seconds=30))
    pump(300)
    assert window.recording_id() is None
    m2 = meetings.Meetings(window)  # Echo restarted: still skipped
    assert m2.is_skipped(ev)
    cfg = config.load()
    cfg.auto_record = False
    config.save(cfg)
    m.skip(ev, False)
    assert not m.will_record(ev)
    window.recorder_panel.start()  # the user records by hand during the meeting
    assert wait_until(lambda: window.recording_id() is not None)
    rid = window.recording_id()
    pump(600)
    window.stop_recording()
    assert wait_until(lambda: calendar.event_of(lib.get(rid)) is not None, 10)  # matched by its time
    assert lib.get(rid).meta.title == "Roadmap review"  # a recording made just before the meeting is it

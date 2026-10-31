"""The calendar in the window: fetched every few minutes, each recording given its event, and the
meetings with a video link recorded when they start.

Echo must be running for a meeting to be recorded, which is what "Keep Echo running in the tray"
is for. A meeting is started at most once: when the user stops it early, or presses Skip on the
home before it starts, Studio leaves it alone. Both are kept in a small state file, so
restarting Echo in the middle of a meeting does not start it again.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from echo_app import paths
from echo_app.fsutil import atomic_write_json, read_json
from echo_app.ui.common import run_task

from . import calendar, config, ics

log = logging.getLogger(__name__)

TICK_MS = 20_000
START_WINDOW_S = 10 * 60  # a meeting found already running (Echo opened late) is recorded this far in
STOP_AFTER_S = calendar.AFTER_END_S  # past the event's end, a recording Studio started is stopped
KEEP_DAYS = 3  # how long a started or skipped meeting is remembered


def key(ev: ics.Event) -> str:
    return f"{ev.uid}@{ev.start.isoformat()}"


def _state_path():
    return paths.state_dir() / "studio-meetings.json"


class Meetings(QObject):
    changed = Signal()  # the calendar was read again, or a meeting was skipped or started
    message = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.library = window.library
        self.active: tuple[str, ics.Event] | None = None  # (recording id, event) Studio is recording
        self._starting: ics.Event | None = None
        self._state = self._load()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self.tick)
        window.recorder_panel.started.connect(self._started)
        window.recorder_panel.stopped.connect(self._stopped)

    def start(self):
        """Begin reading the calendar (now, then every few minutes) and watching for meetings."""
        if not calendar.enabled():
            self._refresh_timer.stop()
            self._tick_timer.stop()
            self.changed.emit()
            return
        self.refresh()
        self._refresh_timer.start(calendar.REFRESH_MINUTES * 60_000)
        self._tick_timer.start(TICK_MS)

    def refresh(self):
        def done(errors):
            for e in errors:
                log.warning("calendar: %s", e)
            self.changed.emit()
            self.tick()

        run_task(calendar.refresh, on_done=done, on_error=lambda msg: log.warning("calendar: %s", msg))

    # ---- what the home shows ----
    def upcoming(self, now: datetime | None = None) -> list[ics.Event]:
        return calendar.upcoming(now) if calendar.enabled() else []

    def next_event(self, now: datetime | None = None) -> ics.Event | None:
        """The meeting on now or next, today or tomorrow."""
        evs = calendar.upcoming(now, hours=36) if calendar.enabled() else []
        return evs[0] if evs else None

    def will_record(self, ev: ics.Event) -> bool:
        return (config.load().auto_record and bool(ev.link) and key(ev) not in self._state["skipped"]
                and key(ev) not in self._state["started"])

    def skip(self, ev: ics.Event, on: bool = True):
        k = key(ev)
        if on:
            self._state["skipped"][k] = datetime.now().astimezone().isoformat()
        else:
            self._state["skipped"].pop(k, None)
        self._save()
        self.changed.emit()

    def is_skipped(self, ev: ics.Event) -> bool:
        return key(ev) in self._state["skipped"]

    # ---- recording the meetings ----
    def tick(self, now: datetime | None = None):
        now = now or datetime.now().astimezone()
        if self.active is not None:
            rid, ev = self.active
            if self.window.recording_id() == rid and now > ev.end + timedelta(seconds=STOP_AFTER_S):
                self.window.stop_recording()
                self.message.emit(f"Stopped recording “{ev.title}”: the meeting ended {STOP_AFTER_S // 60} "
                                  "minutes ago.")
            return
        if self.window.recording_id() is not None or self._starting is not None:
            return  # the user is recording something: leave it
        for ev in self.upcoming(now):
            if ev.start <= now < min(ev.end, ev.start + timedelta(seconds=START_WINDOW_S)) and self.will_record(ev):
                self._starting = ev
                if self.window.start_recording(ev.title):
                    self._state["started"][key(ev)] = now.isoformat()
                    self._save()
                else:
                    self._starting = None
                return

    def _started(self, rid: str):
        ev, self._starting = self._starting, None
        if ev is None:
            return
        self.active = (rid, ev)
        rec = self.library.get(rid)
        if rec is not None:
            calendar.attach(rec, ev)
        self.message.emit(f"Recording “{ev.title}”, from your calendar.")
        tray = getattr(self.window, "tray", None)
        if tray is not None and not self.window.isVisible():
            tray.showMessage("Echo", f"Recording “{ev.title}”, from your calendar. Stop it from the tray.")
        self.changed.emit()

    def _stopped(self, rid: str):
        was_ours = self.active is not None and self.active[0] == rid
        self.active = None
        if not was_ours and calendar.enabled():
            run_task(lambda: self._attach(rid), on_done=lambda _r: self.changed.emit())
        else:
            self.changed.emit()

    def _attach(self, rid: str):
        rec = self.library.get(rid)
        return calendar.attach_if_found(rec) if rec is not None else None

    def transcribed(self, rid: str):
        """Before the summary: the recording's event (an imported one may match too) and the emails
        the calendar teaches about the people named in it."""
        rec = self.library.get(rid)
        if rec is None:
            return
        try:
            calendar.attach_if_found(rec)
            calendar.learn_emails(self.library, rec)
        except OSError as e:
            log.warning("calendar for %s: %s", rid, e)

    # ---- state ----
    def _load(self) -> dict:
        try:
            d = read_json(_state_path())
        except (OSError, ValueError):
            d = {}
        cutoff = datetime.now().astimezone() - timedelta(days=KEEP_DAYS)
        out = {}
        for part in ("started", "skipped"):
            out[part] = {}
            for k, when in (d.get(part) or {}).items() if isinstance(d, dict) else []:
                try:
                    if datetime.fromisoformat(when) >= cutoff:
                        out[part][k] = when
                except (TypeError, ValueError):
                    pass
        return out

    def _save(self):
        try:
            atomic_write_json(_state_path(), self._state, mkdir=True)
        except OSError as e:
            log.warning("meetings state: %s", e)

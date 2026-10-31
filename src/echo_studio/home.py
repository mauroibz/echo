"""Studio's home: the next meeting from the calendar (or the one being recorded), and the minutes
of past meetings as a timeline. It shows what the calendar and the recordings say, nothing more:
no suggestions, no reminders."""

from __future__ import annotations

import re
from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QMouseEvent
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from echo_app.ui import theme
from echo_app.ui.common import fmt_duration

from . import calendar, data, summary
from .widgets import Avatar, AvatarStack, Hero, TimelineDot, label, minutes_long

MINUTES_SHOWN = 12
DESCRIPTION_LINES = 3


def _clear(lay):
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


def agenda(description: str) -> str:
    """The invitation's own words: no links, dial-in numbers or the video call's boilerplate."""
    keep = [ln.strip() for ln in description.splitlines()
            if ln.strip() and "http" not in ln and not re.search(r"\d{3}[\s-]?\d{3}[\s-]?\d{3,}", ln)
            and not re.match(r"(?i)(join|únete|unirse|meeting id|id de reuni|passcode|código|─|_{4,}|-{4,})", ln.strip())]
    return "\n".join(keep[:DESCRIPTION_LINES])


def when_label(ev, now: datetime) -> str:
    """"FRIDAY 31 · UP NEXT IN 25 MIN", "NOW", "TOMORROW · 09:30"."""
    start = ev.start.astimezone(now.tzinfo)
    if ev.start <= now < ev.end:
        return "NOW"
    mins = int((ev.start - now).total_seconds() // 60)
    day = start.date()
    head = "TODAY" if day == now.date() else "TOMORROW" if (day - now.date()).days == 1 else f"{start:%A %d}".upper()
    if mins < 60:
        return f"{head} · UP NEXT IN {max(1, mins)} MIN"
    if mins < 180:
        return f"{head} · UP NEXT IN {mins // 60} H {mins % 60:02d}"
    return f"{head} · UP NEXT"


class MinutesCard(QFrame):
    clicked = Signal(str)

    def __init__(self, rec, lib):
        super().__init__()
        self.rid = rec.id
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Minutes of {rec.meta.title}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(label(rec.meta.title, 1.2, QFont.Weight.ExtraBold))
        bits = [minutes_long(rec.meta.duration)]
        d = summary.load(rec)
        if d and d.get("template"):
            bits.append(d["template"])
        top.addWidget(label(" · ".join(bits), dim=True))
        top.addStretch(1)
        lay.addLayout(top)
        text = data.excerpt(d["text"]) if d else ""
        if text:
            lay.addWidget(label(text, 1.0, display=False, wrap=True))
        names = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n]
        n_items = len(data.action_items(rec))
        if names or n_items:
            row = QHBoxLayout()
            row.setSpacing(10)
            if names:
                row.addWidget(AvatarStack(names, 26))
            if n_items:
                chip = label(f"{n_items} action item{'s' if n_items != 1 else ''}", 0.9, QFont.Weight.Bold)
                chip.setStyleSheet(f"color: {theme.current().accent_deep}; background: {theme.current().accent_soft};"
                                   " border-radius: 10px; padding: 2px 10px;")
                row.addWidget(chip)
            row.addStretch(1)
            lay.addLayout(row)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.rid)
        super().mouseReleaseEvent(e)


class HomeScreen(QWidget):
    """The next meeting in a hero band, then the minutes. `open_minutes(rid)` shows a recording on its
    minutes; `open_settings()` opens Settings."""

    def __init__(self, window, meetings, open_minutes, open_settings):
        super().__init__()
        self.window, self.meetings = window, meetings
        self.library = window.library
        self.open_minutes, self.open_settings = open_minutes, open_settings
        self._notes_rid = None
        self.setObjectName("content")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("content")
        scroll.setWidget(body)
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.hero = Hero()
        self.hero_lay = QHBoxLayout(self.hero)
        self.hero_lay.setContentsMargins(44, 34, 44, Hero.WAVE_H + 26)
        self.hero_lay.setSpacing(32)
        self.body.addWidget(self.hero)
        minutes = QWidget()
        self.minutes = QVBoxLayout(minutes)
        self.minutes.setContentsMargins(44, 8, 44, 40)
        self.minutes.setSpacing(4)
        self.body.addWidget(minutes)
        self.body.addStretch(1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        meetings.changed.connect(self.refresh)
        window.recorder_panel.started.connect(lambda _rid: self.refresh())
        window.recorder_panel.stopped.connect(lambda _rid: QTimer.singleShot(500, self.refresh))
        self.refresh()

    def showEvent(self, e):
        self.refresh()
        self.timer.start(1000)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        self._save_notes()
        super().hideEvent(e)

    def _tick(self):
        if self.window.recording_id() is not None:
            self._update_clock()
        elif datetime.now().second == 0:
            self.refresh()  # the countdown, once a minute

    # ---- the hero ----
    def refresh(self):
        self._save_notes()
        _clear(self.hero_lay)
        self.__dict__.pop("clock", None)
        rid = self.window.recording_id()
        if rid is not None:
            self._recording(rid)
        else:
            self.hero.set_live(False)
            ev = self.meetings.next_event() if calendar.enabled() else None
            if ev is not None:
                self._next(ev)
            else:
                self._empty()
        self._fill_minutes()

    def _recording(self, rid: str):
        self.hero.set_live(True)
        rec = self.library.get(rid)
        active = self.meetings.active
        ev = active[1] if active is not None and active[0] == rid else (calendar.event_of(rec) if rec else None)
        col = QVBoxLayout()
        col.setSpacing(12)
        started = datetime.fromisoformat(rec.meta.created).strftime("%H:%M") if rec else ""
        col.addWidget(label(("RECORDING · STARTED WITH THE CALENDAR AT " if active and active[0] == rid
                             else "RECORDING · SINCE ") + started, 0.9, eyebrow=True))
        self.clock = label("0:00", 6.0, QFont.Weight.ExtraBold, tabular=True)
        col.addWidget(self.clock)
        col.addWidget(label(rec.meta.title if rec else "", 2.2, QFont.Weight.ExtraBold, wrap=True))
        if ev is not None:
            col.addWidget(label(f"Event ends at {ev.end.astimezone():%H:%M}", 1.1, dim=True))
        self.notes = QPlainTextEdit(rec.meta.notes if rec else "")
        self.notes.setPlaceholderText("Your notes: they lead the minutes")
        self.notes.setAccessibleName("Notes")
        self.notes.setFixedHeight(self.notes.fontMetrics().lineSpacing() * 4 + 20)
        self._notes_rid = rid
        col.addWidget(self.notes)
        stop = QPushButton("Stop recording")
        theme.set_role(stop, stop=True)
        stop.clicked.connect(self.window.stop_recording)
        row = QHBoxLayout()
        row.addWidget(stop)
        row.addStretch(1)
        col.addLayout(row)
        self.hero_lay.addLayout(col, 3)
        if ev is not None and ev.attendees:
            self.hero_lay.addLayout(self._invited(ev), 2)
        self._update_clock()

    def _update_clock(self):
        sess = self.window.recorder_panel.session
        if sess is None or not hasattr(self, "clock"):
            return
        try:
            elapsed = sess.status().get("elapsed", 0)
        except Exception:  # noqa: BLE001 - a status read racing the stop
            return
        try:
            self.clock.setText(fmt_duration(elapsed))
        except RuntimeError:
            pass  # the hero was rebuilt as the recording stopped

    def _save_notes(self):
        rid, self._notes_rid = self._notes_rid, None
        if rid is None or not hasattr(self, "notes"):
            return
        rec = self.library.get(rid)
        try:
            text = self.notes.toPlainText().strip()
        except RuntimeError:
            return  # the field went with the hero
        if rec is not None and text != (rec.meta.notes or "").strip():
            rec.update(notes=text)

    def _invited(self, ev) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)
        col.addWidget(label("INVITED", 0.85, eyebrow=True))
        for a in ev.attendees[:8]:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(Avatar(a.name or a.email, 34))
            txt = QVBoxLayout()
            txt.setSpacing(0)
            txt.addWidget(label(a.name or a.email, 1.0, QFont.Weight.Bold))
            if a.name:
                txt.addWidget(label(a.email, 0.9, dim=True))
            row.addLayout(txt)
            row.addStretch(1)
            col.addLayout(row)
        col.addStretch(1)
        return col

    def _next(self, ev):
        now = datetime.now().astimezone()
        col = QVBoxLayout()
        col.setSpacing(12)
        col.addWidget(label(when_label(ev, now), 0.9, eyebrow=True))
        times = QHBoxLayout()
        times.setSpacing(14)
        start = ev.start.astimezone(now.tzinfo)
        times.addWidget(label(f"{start:%H:%M}", 6.0, QFont.Weight.ExtraBold, tabular=True))
        times.addWidget(label(f"to {ev.end.astimezone(now.tzinfo):%H:%M}", 1.5, QFont.Weight.DemiBold, dim=True),
                        0, Qt.AlignmentFlag.AlignBottom)
        times.addStretch(1)
        col.addLayout(times)
        col.addWidget(label(ev.title, 2.4, QFont.Weight.ExtraBold, wrap=True))
        text = agenda(ev.description)
        if text:
            col.addWidget(label(text, 1.0, display=False, dim=True, wrap=True))
        people = [a for a in ev.attendees if a.status != "DECLINED"]
        if people:
            row = QHBoxLayout()
            row.setSpacing(12)
            row.addWidget(AvatarStack([a.name or a.email for a in people], 38, ring="deep_mid"))
            named = [a.name for a in people if a.name]
            rest = len(people) - len(named[:3])
            row.addWidget(label(", ".join(named[:3]) + (f" and {rest} more" if rest > 0 else ""), 1.0, dim=True,
                                wrap=True), 1)
            col.addLayout(row)
        self.hero_lay.addLayout(col, 3)
        side_w = QWidget()
        side_w.setMaximumWidth(320)
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(12)
        side.addStretch(1)
        if ev.link:
            join = QPushButton("Join the call  →")
            join.setAccessibleName("Join the call")
            join.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ev.link)))
            side.addWidget(join)
        status = QHBoxLayout()
        status.setSpacing(10)
        if self.meetings.will_record(ev):
            status.addWidget(label(f"●  Records by itself at {start:%H:%M}", 1.0, QFont.Weight.Bold))
            skip = QPushButton("Skip")
            theme.set_role(skip, quiet=True)
            skip.setToolTip("Do not record this meeting by itself")
            skip.clicked.connect(lambda: self.meetings.skip(ev))
            status.addWidget(skip)
        elif self.meetings.is_skipped(ev):
            status.addWidget(label("Not recording this one", 1.0, dim=True))
            undo = QPushButton("Record it")
            theme.set_role(undo, quiet=True)
            undo.clicked.connect(lambda: self.meetings.skip(ev, False))
            status.addWidget(undo)
        else:
            rec = QPushButton("Record now")
            theme.set_role(rec, quiet=True)
            rec.clicked.connect(lambda: self.window.start_recording(ev.title))
            status.addWidget(rec)
        status.addStretch(1)
        side.addLayout(status)
        self.hero_lay.addWidget(side_w, 2, Qt.AlignmentFlag.AlignBottom)

    def _empty(self):
        col = QVBoxLayout()
        col.setSpacing(12)
        now = datetime.now()
        col.addWidget(label(f"{now:%A %d %B}".upper(), 0.9, eyebrow=True))
        if calendar.enabled():
            col.addWidget(label("Nothing else in your calendar", 2.4, QFont.Weight.ExtraBold, wrap=True))
            col.addWidget(label("Your minutes are below. Record when you need to.", 1.1, dim=True))
        else:
            col.addWidget(label("Your meetings, before and after", 2.4, QFont.Weight.ExtraBold, wrap=True))
            col.addWidget(label("Add your calendar's private address and the next meeting shows here, records "
                                "by itself and names its recording.", 1.1, dim=True, wrap=True))
            row = QHBoxLayout()
            b = QPushButton("Add your calendar")
            b.clicked.connect(self.open_settings)
            row.addWidget(b)
            row.addStretch(1)
            col.addLayout(row)
        self.hero_lay.addLayout(col, 1)

    # ---- the minutes ----
    def _fill_minutes(self):
        _clear(self.minutes)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(label("Minutes", 1.6, QFont.Weight.ExtraBold))
        head.addWidget(label("from your last meetings", 1.0, dim=True), 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        self.minutes.addLayout(head)
        self.minutes.addSpacing(10)
        recs = sorted((r for r in self.library.all() if summary.load(r) is not None),
                      key=lambda r: r.meta.created, reverse=True)[:MINUTES_SHOWN]
        if not recs:
            self.minutes.addWidget(label("Minutes appear here once a recording is summarized.", 1.0, dim=True))
            return
        today = date.today()
        for k, rec in enumerate(recs):
            try:
                when = datetime.fromisoformat(rec.meta.created)
            except ValueError:
                continue
            day = when.date()
            row = QHBoxLayout()
            row.setSpacing(12)
            dcol = QVBoxLayout()
            dcol.setSpacing(0)
            dcol.setContentsMargins(0, 14, 0, 0)
            dl = label("TODAY" if day == today else f"{when:%a %d}".upper(), 0.9, QFont.Weight.ExtraBold)
            if day == today:
                dl.setStyleSheet(f"color: {theme.current().accent_deep};")
            else:
                theme.set_role(dl, dim=True)
            dl.setAlignment(Qt.AlignmentFlag.AlignRight)
            dcol.addWidget(dl)
            tl = label(f"{when:%H:%M}", 0.9, dim=True)
            tl.setAlignment(Qt.AlignmentFlag.AlignRight)
            dcol.addWidget(tl)
            dcol.addStretch(1)
            dw = QWidget()
            dw.setLayout(dcol)
            dw.setFixedWidth(64)
            row.addWidget(dw)
            row.addWidget(TimelineDot(day == today, k == len(recs) - 1))
            card = MinutesCard(rec, self.library)
            card.clicked.connect(self.open_minutes)
            wrap = QVBoxLayout()
            wrap.setContentsMargins(0, 4, 0, 12)
            wrap.addWidget(card)
            row.addLayout(wrap, 1)
            self.minutes.addLayout(row)

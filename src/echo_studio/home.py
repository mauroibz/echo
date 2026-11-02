"""Studio's Briefing: the next meeting from the calendar (or the one being recorded), the meetings
coming up with a switch each for whether it is recorded, and the minutes of past meetings as a
timeline of cards (the gist, the action items, your notes). It shows what the calendar and the
recordings say, nothing more: no suggestions, no reminders."""

from __future__ import annotations

import re
from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QMouseEvent
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from echo_app.ui import theme
from echo_app.ui.common import fmt_duration

from . import actions, calendar, data, marks, summary
from .actions_ui import fmt_due
from .widgets import Avatar, AvatarStack, Hero, StarButton, TimelineDot, Toggle, label, minutes_long

MINUTES_SHOWN = 12
DESCRIPTION_LINES = 3
CARD_ITEMS = 3  # action items shown on a minutes card; the rest are counted
NOTES_CHARS = 180
COMING_DAYS = 7
COMING_SHOWN = 14


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
    """A meeting's minutes at a glance: the gist, the first action items with their owners, your
    notes, who was there, its tags and a star. Clicking it opens the minutes."""

    clicked = Signal(str)

    def __init__(self, rec, lib, footer: bool = True):
        super().__init__()
        self.rid = rec.id
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Minutes of {rec.meta.title}")
        t = theme.current()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 14, 14, 16)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(label(rec.meta.title, 1.2, QFont.Weight.ExtraBold, wrap=True), 1)
        bits = [minutes_long(rec.meta.duration)]
        d = summary.load(rec)
        if d and d.get("template"):
            bits.append(d["template"])
        top.addWidget(label(" · ".join(bits), dim=True), 0, Qt.AlignmentFlag.AlignTop)
        saved = actions.load(rec)
        st = actions.status(saved)
        self.processed = bool(d) and st["processed"]
        if self.processed:
            chip = label("✓ Processed", 0.82, QFont.Weight.ExtraBold)
            chip.setToolTip("Marked ready and every item is in your tracker: you can archive the call")
            chip.setStyleSheet(f"color: {t.accent_deep}; background: {t.accent_soft}; border-radius: 9px;"
                               " padding: 1px 8px;")
            top.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        self.star = StarButton(marks.starred(rec))
        self.star.starred.connect(lambda on, r=rec: marks.set_starred(r, on))
        top.addWidget(self.star, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)
        text = data.excerpt(d["text"]) if d else ""
        if text:
            lay.addWidget(label(text, 1.0, display=False, wrap=True))
        items = [it for it in (saved or {}).get("items", []) if not it["discarded"]]
        if items:
            box = QFrame()
            box.setStyleSheet(f"QFrame {{ background: {t.raised}; border-radius: 12px; }} "
                              "QLabel { background: transparent; }")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 10)
            bl.setSpacing(5)
            head = f"ACTION ITEMS · {len(items)}"
            if st["sent"] and not self.processed:
                head += f" · {st['sent']} SENT"
            if st["ready"]:
                head += f" · {st['ready']} READY"
            if st["failed"]:
                head += f" · {st['failed']} FAILED"
            bl.addWidget(label(head, 0.8, QFont.Weight.ExtraBold, eyebrow=True))
            for it in items[:CARD_ITEMS]:
                row = QHBoxLayout()
                row.setSpacing(8)
                if it["owner"]:
                    row.addWidget(Avatar(it["owner"], 20), 0, Qt.AlignmentFlag.AlignTop)
                sent = "✓  " if it["state"] == actions.SENT else ""
                row.addWidget(label(sent + it["text"], 0.95, QFont.Weight.DemiBold, wrap=True), 1)
                if it["due"]:
                    row.addWidget(label(fmt_due(it["due"]), 0.85, dim=True), 0, Qt.AlignmentFlag.AlignTop)
                bl.addLayout(row)
            if len(items) > CARD_ITEMS:
                bl.addWidget(label(f"+{len(items) - CARD_ITEMS} more", 0.85, QFont.Weight.Bold, dim=True))
            lay.addWidget(box)
        notes = " ".join((rec.meta.notes or "").split())
        if notes:
            cut = notes if len(notes) <= NOTES_CHARS else notes[:NOTES_CHARS].rsplit(" ", 1)[0] + "…"
            n = label(f"Your notes: {cut}", 0.95, display=False, wrap=True, dim=True)
            lay.addWidget(n)
        names = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n]
        tags = [tg for tg in rec.meta.tags if not tg.lower().startswith("template:")]
        if footer and (names or tags):  # a person's page has its own tag editor and no avatars
            row = QHBoxLayout()
            row.setSpacing(10)
            if names:
                row.addWidget(AvatarStack(names, 26))
            for tg in tags[:4]:
                chip = label(f"#{tg}", 0.85, QFont.Weight.Bold)
                chip.setStyleSheet(f"color: {t.accent_deep}; background: {t.accent_soft}; border-radius: 9px;"
                                   " padding: 1px 8px;")
                row.addWidget(chip)
            row.addStretch(1)
            lay.addLayout(row)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.rid)
        super().mouseReleaseEvent(e)


class ComingUp(QWidget):
    """The meetings of the next days, by day, each with a switch: recorded when it starts or not.
    A meeting with a video link starts on (when recording meetings is on in Settings); one without
    starts off and can be turned on (an in-person meeting)."""

    def __init__(self, meetings):
        super().__init__()
        self.meetings = meetings
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)

    def fill(self, now: datetime | None = None):
        _clear(self.lay)
        now = now or datetime.now().astimezone()
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(label("Coming up", 1.6, QFont.Weight.ExtraBold))
        head.addStretch(1)
        head.addWidget(label("records?", 0.9, dim=True), 0, Qt.AlignmentFlag.AlignBottom)
        self.lay.addLayout(head)
        self.lay.addSpacing(10)
        evs = calendar.upcoming(now, hours=COMING_DAYS * 24) if calendar.enabled() else []
        if not evs:
            self.lay.addWidget(label(f"Nothing in the next {COMING_DAYS} days.", 1.0, dim=True))
            return
        day = None
        for ev in evs[:COMING_SHOWN]:
            start = ev.start.astimezone(now.tzinfo)
            if start.date() != day:
                day = start.date()
                delta = (day - now.date()).days
                when = "TODAY" if delta == 0 else "TOMORROW" if delta == 1 else f"{start:%A %d}".upper()
                if self.lay.count() > 2:
                    self.lay.addSpacing(8)
                self.lay.addWidget(label(when, 0.8, QFont.Weight.ExtraBold, eyebrow=True))
            self.lay.addWidget(self._row(ev, start, now))
        if len(evs) > COMING_SHOWN:
            self.lay.addWidget(label(f"+{len(evs) - COMING_SHOWN} more this week", 0.9, dim=True))

    def _row(self, ev, start: datetime, now: datetime) -> QWidget:
        row = QFrame()
        row.setObjectName("card")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 10, 12, 10)
        rl.setSpacing(12)
        tl = label(f"{start:%H:%M}", 1.05, QFont.Weight.ExtraBold, tabular=True)
        tl.setFixedWidth(46)
        rl.addWidget(tl, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(label(ev.title, 1.0, QFont.Weight.Bold, wrap=True))
        people = [a.name or a.email.split("@")[0] for a in ev.attendees if a.status != "DECLINED"]
        bits = [f"{minutes_long((ev.end - ev.start).total_seconds())}"]
        bits.append("video call" if ev.link else "no video link")
        if people:
            bits.append(", ".join(people[:2]) + (f" +{len(people) - 2}" if len(people) > 2 else ""))
        col.addWidget(label(" · ".join(bits), 0.88, dim=True, wrap=True))
        rl.addLayout(col, 1)
        if self.meetings.active is not None and self.meetings.active[1].uid == ev.uid \
                and self.meetings.active[1].start == ev.start:
            st = label("● REC", 0.8, QFont.Weight.ExtraBold)
            st.setStyleSheet(f"color: {theme.current().coral_deep};")
            rl.addWidget(st, 0, Qt.AlignmentFlag.AlignVCenter)
        elif self.meetings.was_started(ev):
            rl.addWidget(label("Recorded", 0.85, dim=True), 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            on = self.meetings.will_record(ev)
            sw = Toggle(on, f"Record “{ev.title}” when it starts")
            sw.toggled.connect(lambda v, e=ev: self.meetings.set_record(e, v))
            rl.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
        return row


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
        below = QHBoxLayout()
        below.setContentsMargins(44, 8, 44, 40)
        below.setSpacing(32)
        minutes = QWidget()
        self.minutes = QVBoxLayout(minutes)
        self.minutes.setContentsMargins(0, 0, 0, 0)
        self.minutes.setSpacing(4)
        below.addWidget(minutes, 3, Qt.AlignmentFlag.AlignTop)
        self.coming = ComingUp(meetings)
        self.coming.setMaximumWidth(400)
        self.coming.setMinimumWidth(280)
        below.addWidget(self.coming, 2, Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(below)
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
        self.coming.setVisible(calendar.enabled())
        if calendar.enabled():
            self.coming.fill()

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
            skip = QPushButton("Don't record")
            theme.set_role(skip, quiet=True)
            skip.setToolTip("Do not record this meeting by itself")
            skip.clicked.connect(lambda: self.meetings.set_record(ev, False))
            status.addWidget(skip)
        elif self.meetings.is_skipped(ev) or (ev.start > datetime.now().astimezone()
                                               and not self.meetings.was_started(ev)):
            status.addWidget(label("Not recording this one", 1.0, dim=True))
            undo = QPushButton("Record it")
            theme.set_role(undo, quiet=True)
            undo.setToolTip("Record this meeting when it starts")
            undo.clicked.connect(lambda: self.meetings.set_record(ev, True))
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

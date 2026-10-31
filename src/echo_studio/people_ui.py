"""Studio's People: everyone Echo knows, and a page per person with their meetings, their part in
each, the action items assigned to them and the notes, keyed by their email. Informative only:
nothing here is a task to keep up."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from echo_app import people
from echo_app.index import Index
from echo_app.library import fold_tag
from echo_app.ui import theme
from echo_app.ui.common import fmt_date

from . import actions, data, parts, summary
from .actions_ui import ActionList
from .home import MinutesCard, _clear
from .widgets import Avatar, Hero, label

ROLE_NAME = Qt.ItemDataRole.UserRole + 1
MEETINGS_SHOWN = 8


def meetings_of(lib, index, name: str) -> list[dict]:
    """A person's meetings, newest first: the recordings they speak in (as the index knows them),
    those where a speaker has their name, and those whose calendar event invited their email; each
    with the others in it, the minutes' excerpt and the person's part."""
    from . import calendar

    want = fold_tag(name)
    email = people.load(lib, name).email
    ids = [r["id"] for r in people.recordings_of(index, name)]
    for rec in lib.all():
        if rec.id in ids:
            continue
        if any(fold_tag(n) == want for n in rec.meta.speakers.values() if n):
            ids.append(rec.id)
        elif email and rec.path(calendar.EVENT_FILE).exists():
            ev = calendar.event_of(rec)
            if ev is not None and any(a.email == email for a in ev.attendees):
                ids.append(rec.id)
    out = []
    for rid in ids:
        rec = lib.get(rid)
        if rec is None:
            continue
        d = summary.load(rec)
        others = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n and fold_tag(n) != want]
        out.append({"rec": rec, "id": rec.id, "title": rec.meta.title, "created": rec.meta.created,
                    "others": others, "excerpt": data.excerpt(d["text"]) if d else "",
                    "part": parts.part_of(rec, name), "minutes": d is not None})
    return sorted(out, key=lambda m: m["created"], reverse=True)


def _day(iso: str) -> str:
    from datetime import date, datetime

    try:
        d = datetime.fromisoformat(iso).date()
    except ValueError:
        return "—"
    return f"{d:%b %-d}" if d.year == date.today().year else f"{d:%b %Y}"


class PersonPage(QWidget):
    def __init__(self, library, open_minutes, open_profile):
        super().__init__()
        self.library, self.open_minutes, self.open_profile = library, open_minutes, open_profile
        self.name: str | None = None
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
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)

    def show_person(self, name: str | None):
        self._save_notes()
        self.name = name
        _clear(self.lay)
        if not name:
            self.lay.addStretch(1)
            return
        prof = people.load(self.library, name)
        idx = Index(self.library)
        try:
            idx.sync()
            meetings = meetings_of(self.library, idx, name)
        finally:
            idx.close()
        items = actions.assigned_to(self.library, name)

        hero = Hero()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(44, 30, 44, Hero.WAVE_H + 20)
        hl.setSpacing(24)
        hl.addWidget(Avatar(name, 96, ring="foam"), 0, Qt.AlignmentFlag.AlignTop)
        who = QVBoxLayout()
        who.setSpacing(4)
        who.addWidget(label(name, 2.6, QFont.Weight.ExtraBold, wrap=True))
        if prof.email:
            em = label(prof.email, 1.15, QFont.Weight.Bold)
            em.setStyleSheet(f"color: {theme.current().foam};")
            who.addWidget(em)
        from echo_app import dictionary

        entry = dictionary.current().find(name)
        if entry and entry.aliases:
            who.addWidget(label("Also heard as " + ", ".join(entry.aliases), 1.0, dim=True))
        who.addStretch(1)
        hl.addLayout(who, 1)
        first = min((m["created"] for m in meetings), default=None)
        for value, what in ((str(len(meetings)), "MEETINGS"), (str(len(items)), "ACTION ITEMS"),
                            (_day(first) if first else "—", "FIRST HEARD")):
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(value, 2.4, QFont.Weight.ExtraBold, tabular=True))
            col.addWidget(label(what, 0.8, eyebrow=True))
            col.addStretch(1)
            hl.addLayout(col)
        self.lay.addWidget(hero)

        cols = QHBoxLayout()
        cols.setContentsMargins(44, 8, 44, 40)
        cols.setSpacing(28)
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(label("Meetings with them", 1.4, QFont.Weight.ExtraBold))
        if not meetings:
            left.addWidget(label("Not named as a speaker in any recording yet.", 1.0, dim=True))
        for m in meetings[:MEETINGS_SHOWN]:
            left.addWidget(self._meeting(m))
        if len(meetings) > MEETINGS_SHOWN:
            left.addWidget(label(f"+{len(meetings) - MEETINGS_SHOWN} earlier", 1.0, QFont.Weight.Bold, dim=True))
        left.addStretch(1)
        cols.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(label("Action items assigned to them", 1.15, QFont.Weight.ExtraBold, wrap=True))
        lst = ActionList(with_recording=True, empty="None assigned to them.")
        lst.set_items(items)
        lst.play.connect(lambda rid, at: self.open_minutes(rid, at))
        right.addWidget(lst)
        right.addWidget(label("As said in each meeting. Echo does not track whether they got done.", 0.9,
                              dim=True, wrap=True))
        right.addSpacing(10)
        notes_card = QFrame()
        notes_card.setObjectName("card")
        notes_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nl = QVBoxLayout(notes_card)
        nl.setContentsMargins(18, 14, 18, 14)
        nl.addWidget(label("Notes", 1.05, QFont.Weight.ExtraBold))
        self.notes = QPlainTextEdit(prof.notes)
        self.notes.setObjectName("plain")
        self.notes.setPlaceholderText("Who they are, their role, anything worth remembering")
        self.notes.setAccessibleName("Notes")
        self.notes.setFixedHeight(self.notes.fontMetrics().lineSpacing() * 5 + 16)
        self.notes.installEventFilter(self)
        nl.addWidget(self.notes)
        right.addWidget(notes_card)
        id_card = QFrame()
        id_card.setObjectName("card")
        id_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        il = QVBoxLayout(id_card)
        il.setContentsMargins(18, 14, 18, 14)
        il.addWidget(label("Email, the key Echo uses", 0.95, QFont.Weight.Bold, dim=True))
        self.email = QLineEdit(prof.email)
        self.email.setPlaceholderText("name@example.com")
        self.email.setAccessibleName("Email")
        self.email.editingFinished.connect(self._save_email)
        il.addWidget(self.email)
        il.addWidget(label("Calendar attendees with this email are offered as them when naming speakers.", 0.9,
                           dim=True, wrap=True))
        more = QPushButton("Aliases, tags and voice…")
        more.clicked.connect(lambda: self.open_profile(self.name))
        il.addWidget(more, 0, Qt.AlignmentFlag.AlignLeft)
        right.addWidget(id_card)
        right.addStretch(1)
        cols.addLayout(right, 2)
        self.lay.addLayout(cols)
        self.lay.addStretch(1)

    def _meeting(self, m: dict) -> QWidget:
        card = MinutesCard(m["rec"], self.library)
        card.clicked.connect(lambda rid: self.open_minutes(rid, None))
        lay = card.layout()
        meta = f"{fmt_date(m['created'])}" + (f" · with {', '.join(m['others'][:3])}" if m["others"] else
                                                " · just you two" if m["minutes"] else "")
        lay.insertWidget(1, label(meta, 0.95, dim=True))
        if m["part"]:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            lay.addWidget(sep)
            part = label(f"Their part: {m['part']}", 1.0, display=False, wrap=True)
            part.setStyleSheet(f"color: {theme.current().accent_deep};")
            lay.addWidget(part)
        return card

    def eventFilter(self, obj, event):
        if obj is getattr(self, "notes", None) and event.type() == QEvent.Type.FocusOut:
            self._save_notes()
        return super().eventFilter(obj, event)

    def _save_notes(self):
        if not self.name or not hasattr(self, "notes"):
            return
        try:
            text = self.notes.toPlainText().strip()
        except RuntimeError:
            return
        prof = people.load(self.library, self.name)
        if prof.notes != text:
            prof.notes = text
            people.save(self.library, prof)

    def _save_email(self):
        prof = people.load(self.library, self.name)
        typed = self.email.text().strip()
        email = people.clean_email(typed)
        if typed and not email:
            self.email.setText(prof.email)
            return
        other = people.by_email(self.library, email)
        if other is not None and fold_tag(other.name) != fold_tag(prof.name):
            QMessageBox.information(self, "People", f"{email} is already {other.name}'s email.")
            self.email.setText(prof.email)
            return
        if prof.email != email:
            prof.email = email
            people.save(self.library, prof)
        self.email.setText(email)


class PeopleScreen(QWidget):
    """Everyone Echo knows at the left, most meetings first; the chosen person's page at the right."""

    def __init__(self, library, open_minutes, open_profile):
        super().__init__()
        self.library = library
        self.setObjectName("content")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(20, 22, 8, 18)
        ll.setSpacing(10)
        ll.addWidget(label("People", 1.9, QFont.Weight.ExtraBold))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter people")
        self.filter.setClearButtonEnabled(True)
        self.filter.setAccessibleName("Filter people")
        self.filter.textChanged.connect(lambda _t: self._fill())
        ll.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setAccessibleName("People")
        self.list.setObjectName("studioPeople")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self._style_list()
        self.list.currentItemChanged.connect(lambda item, _p: self.page.show_person(item.data(ROLE_NAME) if item else None))
        ll.addWidget(self.list, 1)
        split.addWidget(left)
        self.page = PersonPage(library, open_minutes, open_profile)
        split.addWidget(self.page)
        split.setSizes([260, 900])
        split.setStretchFactor(1, 1)
        lay.addWidget(split)
        self._people: list[people.Person] = []

    def _style_list(self):
        t = self._tokens = theme.current()
        self.list.setStyleSheet(f"""
            QListWidget#studioPeople {{ background: transparent; border: none; }}
            QListWidget#studioPeople::item {{ padding: 9px 12px; border-radius: 10px; color: {t.ink}; }}
            QListWidget#studioPeople::item:hover {{ background: {t.raised}; }}
            QListWidget#studioPeople::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
        """)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.PaletteChange and self._tokens is not theme.current():
            self._style_list()
        super().changeEvent(e)

    def showEvent(self, e):
        self.reload()
        super().showEvent(e)

    def reload(self, select: str | None = None):
        idx = Index(self.library)
        try:
            idx.sync()
            self._people = people.everyone(self.library, idx)
        finally:
            idx.close()
        self._fill(select or (self.page.name if self.page.name else None))

    def _fill(self, select: str | None = None):
        q = fold_tag(self.filter.text().strip())
        keep = select or (self.list.currentItem().data(ROLE_NAME) if self.list.currentItem() else None)
        self.list.blockSignals(True)
        self.list.clear()
        row = 0
        emails = {fold_tag(pr.name): pr.email for pr in people.profiles(self.library)}  # as saved now
        for p in self._people:
            email = emails.get(fold_tag(p.name), "")
            if q and q not in fold_tag(p.name) and q not in email:
                continue
            item = QListWidgetItem(f"{p.name}" + (f"   ·   {p.recordings}" if p.recordings else ""))
            item.setData(ROLE_NAME, p.name)
            if email:
                item.setToolTip(email)
            self.list.addItem(item)
            if keep and fold_tag(p.name) == fold_tag(keep):
                row = self.list.count() - 1
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(row)
            self.page.show_person(self.list.currentItem().data(ROLE_NAME))
        else:
            self.page.show_person(None)

    def select(self, name: str):
        self.reload(name)

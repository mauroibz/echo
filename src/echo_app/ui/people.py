"""The People window: everyone Echo knows, and a profile per person.

A profile shows and keeps notes and tags (``people.py``, files in the data folder), the person's
aliases (the dictionary's), their recordings with how long they spoke, and their voice: a few
seconds from their latest recording, played by a player of this window's own so the main one is
untouched, and "Forget voice" for a voice Echo learned wrong.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget)

from .. import dictionary, extensions, people
from ..audio.playback import Playback
from ..index import Index
from ..library import Library, fold_tag
from . import theme
from .common import fmt_date, fmt_duration, icon
from .tags import TagEditor

log = logging.getLogger(__name__)

SAMPLE_S = 6.0  # as the naming bar: enough to know a voice
ROLE_NAME = Qt.ItemDataRole.UserRole + 1
ROLE_ID = Qt.ItemDataRole.UserRole + 2


class PeopleDialog(QDialog):
    open_recording = Signal(str)  # recording id, to show in the main window

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self.setWindowTitle("People")
        self.resize(900, 580)
        self._people: list[people.Person] = []
        self._name: str | None = None
        self._recs: list[dict] = []
        self._playback = Playback()

        split = QSplitter(self)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter people")
        self.filter.setClearButtonEnabled(True)
        self.filter.setAccessibleName("Filter people")
        self.filter.textChanged.connect(lambda _t: self._fill_list(self._name))
        ll.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setAccessibleName("People")
        self.list.currentItemChanged.connect(lambda item, _prev: self._show(item.data(ROLE_NAME) if item else None))
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        self.page = QWidget()
        pl = QVBoxLayout(self.page)
        pl.setContentsMargins(16, 4, 4, 4)
        self.name_label = QLabel()
        self.name_label.setFont(theme.display_font(1.5, QFont.Weight.Bold))
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl.addWidget(self.name_label)
        self.summary = QLabel()
        theme.set_role(self.summary, muted=True)
        pl.addWidget(self.summary)
        voice = QHBoxLayout()
        self.play = QPushButton(icon("play"), "Hear voice")
        self.play.setMinimumWidth(self.play.sizeHint().width() + 24)  # the primary style pads more than the hint
        self.play.setToolTip("A few seconds of them from their latest recording")
        self.play.clicked.connect(self._play_voice)
        voice.addWidget(self.play)
        self.forget = QPushButton("Forget voice")
        self.forget.setToolTip("Echo stops recognizing them; naming them again teaches it anew")
        self.forget.clicked.connect(self._forget_voice)
        voice.addWidget(self.forget)
        voice.addStretch(1)
        pl.addLayout(voice)
        form = QFormLayout()
        self.email = QLineEdit()
        self.email.setPlaceholderText("name@example.com")
        self.email.setToolTip("Matches them to a calendar's attendees and to what extensions keep about them")
        self.email.setAccessibleName("Email")
        self.email.editingFinished.connect(self._save_email)
        form.addRow("Email", self.email)
        self.aliases = QLineEdit()
        self.aliases.setPlaceholderText("Other spellings, separated by commas")
        self.aliases.setToolTip("Transcription writes the name whenever it hears one of these (the dictionary's aliases)")
        self.aliases.editingFinished.connect(self._save_aliases)
        form.addRow("Aliases", self.aliases)
        self.tags = TagEditor()
        self.tags.changed.connect(self._save_tags)
        form.addRow("Tags", self.tags)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Who they are, their role, anything worth remembering")
        self.notes.setAccessibleName("Notes")
        self.notes.setTabChangesFocus(True)
        self.notes.setFixedHeight(self.notes.fontMetrics().lineSpacing() * 5 + 16)
        self.notes.installEventFilter(self)
        form.addRow("Notes", self.notes)
        pl.addLayout(form)
        # What extensions show about the person (person_sections), rebuilt for each person.
        self.sections = QVBoxLayout()
        self.sections.setSpacing(8)
        pl.addLayout(self.sections)
        heading = QLabel("Recordings")
        heading.setFont(theme.display_font(1.0, QFont.Weight.Bold))
        pl.addWidget(heading)
        self.recordings = QListWidget()
        self.recordings.setAccessibleName("Their recordings")
        self.recordings.setToolTip("Double-click to open")
        self.recordings.itemActivated.connect(lambda item: self.open_recording.emit(item.data(ROLE_ID)))
        pl.addWidget(self.recordings, 1)
        split.addWidget(self.page)
        split.setSizes([260, 640])

        outer = QVBoxLayout(self)
        outer.addWidget(split)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.filter.setFocus)
        self.reload()

    def _show_sections(self, name: str):
        while self.sections.count():
            w = self.sections.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for title, widget in extensions.gather("person_sections", name):
            head = QLabel(title)
            head.setFont(theme.display_font(1.0, QFont.Weight.Bold))
            self.sections.addWidget(head)
            self.sections.addWidget(widget)

    # ---- the list ----
    def reload(self, select: str | None = None):
        idx = Index(self.library)
        try:
            idx.sync()
            self._people = people.everyone(self.library, idx)
        finally:
            idx.close()
        self._fill_list(select or self._name)

    def _fill_list(self, select: str | None = None):
        q = fold_tag(self.filter.text().strip())
        self.list.blockSignals(True)
        self.list.clear()
        current = None
        for p in self._people:
            if q and q not in fold_tag(p.name):
                continue
            item = QListWidgetItem(f"{p.name}   {p.recordings}" if p.recordings else p.name)
            item.setData(ROLE_NAME, p.name)
            item.setToolTip(f"Speaks in {p.recordings} recordings" if p.recordings else "In no recording yet")
            self.list.addItem(item)
            if select and fold_tag(p.name) == fold_tag(select):
                current = item
        self.list.blockSignals(False)
        if current is None and self.list.count():
            current = self.list.item(0)
        if current is not None:
            self.list.setCurrentItem(current)
            self._show(current.data(ROLE_NAME))
        else:
            self._show(None)

    def select(self, name: str):
        self.filter.clear()
        self.reload(name)

    # ---- a profile ----
    def _person(self, name: str | None) -> people.Person | None:
        return next((p for p in self._people if name and fold_tag(p.name) == fold_tag(name)), None)

    def _show(self, name: str | None):
        if self._name and name != self._name:
            self._save_notes()
        self._name = name
        p = self._person(name)
        self.page.setVisible(p is not None)
        if p is None:
            return
        prof = people.load(self.library, p.name)
        entry = dictionary.current().find(p.name)
        self.name_label.setText(p.name)
        if p.recordings:
            self.summary.setText(f"Speaks in {p.recordings} recording{'s' if p.recordings != 1 else ''}  ·  "
                                 f"{fmt_duration(p.seconds)} in all  ·  last {fmt_date(p.last)}")
        else:
            self.summary.setText("Not named as a speaker in any recording yet")
        self.aliases.setText(", ".join(entry.aliases) if entry else "")
        self.email.setText(prof.email)
        self.tags.set_known(sorted({t for q in self._people if q.profile for t in q.profile.tags}))
        self.tags.set_tags(prof.tags)
        self.notes.setPlainText(prof.notes)
        self._show_sections(p.name)
        idx = Index(self.library)
        try:
            self._recs = people.recordings_of(idx, p.name)
        finally:
            idx.close()
        self.recordings.clear()
        for r in self._recs:
            item = QListWidgetItem(f"{r['title']}   ·   {fmt_date(r['created'])}   ·   "
                                   f"{fmt_duration(r['seconds'])} spoken")
            item.setData(ROLE_ID, r["id"])
            self.recordings.addItem(item)
        self.play.setEnabled(bool(self._recs))
        self.forget.setEnabled(p.has_voice)

    def eventFilter(self, obj, event):
        if obj is self.notes and event.type() == QEvent.Type.FocusOut:
            self._save_notes()
        return super().eventFilter(obj, event)

    def _profile(self) -> people.Profile | None:
        return people.load(self.library, self._name) if self._name else None

    def _save_notes(self):
        prof = self._profile()
        if prof is not None and prof.notes != self.notes.toPlainText().strip():
            prof.notes = self.notes.toPlainText().strip()
            people.save(self.library, prof)

    def _save_email(self):
        prof = self._profile()
        if prof is None:
            return
        typed = self.email.text().strip()
        email = people.clean_email(typed)
        if typed and not email:
            self.email.setText(prof.email)  # not an address: keep the one saved
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

    def _save_tags(self, tags: list[str]):
        prof = self._profile()
        if prof is None:
            return
        prof.tags = tags
        people.save(self.library, prof)
        self.tags.set_tags(people.load(self.library, prof.name).tags)

    def _save_aliases(self):
        name = self._name
        if not name:
            return
        wanted = [a for a in dict.fromkeys(" ".join(a.split()) for a in self.aliases.text().split(",")) if a]
        entry = dictionary.current().find(name)
        if (entry.aliases if entry else []) == wanted:
            return

        def change(d):
            e = d.add(dictionary.PEOPLE, name)
            e.aliases = [a for a in wanted if a != e.name]

        try:
            dictionary.update(change)
        except OSError as e:
            log.warning("could not save aliases for %s: %s", name, e)

    def _play_voice(self):
        """Their longest passage in their latest recording, the first few seconds of it."""
        for r in self._recs:
            rec = self.library.get(r["id"])
            if rec is None or rec.audio_path is None:
                continue
            segs = [s for i, s in enumerate((rec.transcript() or {}).get("segments") or [])
                    if rec.speaker_at(i, s) == r["number"] and s.get("text")]
            if not segs:
                continue
            sg = max(segs, key=lambda s: float(s.get("end", 0)) - float(s.get("start", 0)))
            start = float(sg.get("start", 0))
            self._playback.load(rec.audio_path, rec.meta.duration or 0, bool(rec.meta.tracks))
            self._playback.play(start, min(float(sg.get("end", 0)), start + SAMPLE_S))
            return

    def _forget_voice(self):
        if self._name:
            dictionary.forget_voice(self._name)
            self.reload(self._name)

    def done(self, r):
        self._save_notes()
        self._playback.stop()
        super().done(r)

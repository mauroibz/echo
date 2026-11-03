"""Action items in the window: in a recording's Action items view and on a person's page, to
polish, check off as done and choose for the team's tracker; on a minutes card, at a glance."""

from __future__ import annotations

import html
from datetime import date

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from echo_app import export
from echo_app.ui import theme
from echo_app.ui.common import fmt_date, icon

from . import actions
from .widgets import Toggle


def fmt_due(day: str) -> str:
    """A due date as said in the meeting: "by Fri Oct 31" within a week, else "by Nov 14" (with the
    year when it is not this one). Never "late": whether it got done is not Echo's to know."""
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return f"by {day}"
    today = date.today()
    delta = (d - today).days
    when = f"{d:%a %b %-d}" if 0 <= delta < 7 else f"{d:%b %-d}" if d.year == today.year else f"{d:%b %-d %Y}"
    return f"by {when}"


def _dim(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    theme.set_role(lbl, dim=True)
    return lbl


def _small_button(ic: str, tip: str) -> QToolButton:
    b = QToolButton()
    b.setIcon(icon(ic))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setAutoRaise(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def _time_pill(at: float) -> QToolButton:
    b = QToolButton()
    b.setObjectName("pill")
    b.setText(export.stamp(at))
    b.setIcon(icon("play", "accent_deep"))
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    b.setToolTip("Play where this came up")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class ItemEditor(QWidget):
    """An item's fields: title, description, owner (one of the recording's speakers, or typed), due
    date, context for whoever picks it up, and a note only for the user."""

    saved = Signal(dict)
    cancelled = Signal()

    def __init__(self, it: dict | None, names: list[str]):
        super().__init__()
        self.setObjectName("actionEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        it = it or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        self.text = QLineEdit(it.get("text", ""))
        self.text.setPlaceholderText("What has to be done")
        self.text.setAccessibleName("Action item")
        lay.addWidget(self.text)
        self.description = _area(it.get("description", ""), "What exactly, why, and the details that were said",
                                 "Description", 3)
        lay.addWidget(self.description)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.owner = QComboBox()
        self.owner.setEditable(True)
        self.owner.addItems([""] + [n for n in names if n])
        self.owner.setCurrentText(it.get("owner", ""))
        self.owner.lineEdit().setPlaceholderText("Owner")
        self.owner.setAccessibleName("Owner")
        row.addWidget(self.owner, 1)
        self.due = QLineEdit(it.get("due", ""))
        self.due.setPlaceholderText("YYYY-MM-DD")
        self.due.setAccessibleName("Due date")
        self.due.setMaximumWidth(130)
        row.addWidget(self.due)
        lay.addLayout(row)
        self.context = _area(it.get("context", ""), "Context for whoever picks it up", "Context", 2)
        lay.addWidget(self.context)
        self.note = _area(it.get("note", ""), "A note for yourself: stays in Echo", "Your note", 2)
        lay.addWidget(self.note)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled.emit)
        btns.addWidget(cancel)
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save)
        btns.addWidget(self.save_btn)
        lay.addLayout(btns)
        self.text.textChanged.connect(self._check)
        self.due.textChanged.connect(self._check)
        self.text.returnPressed.connect(self._save)
        self._check()

    def _check(self):
        due = self.due.text().strip()
        try:
            ok_due = not due or bool(date.fromisoformat(due))
        except ValueError:
            ok_due = False
        self.save_btn.setEnabled(bool(self.text.text().strip()) and ok_due)

    def _save(self):
        if self.save_btn.isEnabled():
            self.saved.emit({"text": self.text.text(), "description": self.description.toPlainText(),
                             "owner": self.owner.currentText(), "due": self.due.text().strip(),
                             "context": self.context.toPlainText(), "note": self.note.toPlainText()})


def _area(text: str, placeholder: str, name: str, lines: int) -> QPlainTextEdit:
    a = QPlainTextEdit(text)
    a.setPlaceholderText(placeholder)
    a.setAccessibleName(name)
    a.setTabChangesFocus(True)
    a.setFixedHeight(a.fontMetrics().lineSpacing() * lines + 14)
    return a


class ActionList(QWidget):
    """Action items to work on: a recording's (its Action items view) or a person's across
    recordings. Each can be checked off as done, switched on for the tracker, edited, given context
    or a note and discarded; discarded ones fold into one line with Restore. A recording's list can
    also be added to. `compact` leaves the description, context and note out. A time button plays
    where an item came up."""

    play = Signal(str, float)  # recording id, seconds
    changed = Signal()  # an actions.json was written
    relaid = Signal()  # rows or the editor changed, so the height may have

    def __init__(self, editable: bool = False, with_recording: bool = False, empty: str = "No action items.",
                 library=None, compact: bool = False):
        super().__init__()
        self.setObjectName("actionList")
        self.editable = editable
        self.with_recording = with_recording
        self.empty = empty
        self.library = library
        self.compact = compact
        self.rec = None
        self.source = lambda: []  # the items as saved now, discarded ones included
        self.items: list[dict] = []
        self.editing: tuple[str, int] | None = None  # (recording id, index); ("", -1) for a new item
        self.show_discarded = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)
        self._style()

    def _style(self):
        t = self._tokens = theme.current()
        self.setStyleSheet(f"""
            QFrame#actionItem {{ background: {t.raised}; border: 1px solid {t.line}; border-radius: 12px; }}
            QFrame#actionItem[discarded="true"] {{ background: transparent; }}
            QFrame#actionItem[done="true"] {{ background: transparent; }}
            QFrame#actionItem QCheckBox {{ spacing: 0; padding-top: 2px; }}
            QWidget#actionEditor {{ background: {t.surface}; border: 1px solid {t.accent}; border-radius: 12px; }}
            QLabel#actionNote {{ background: {theme.rgba('amber', 0.16)}; border-radius: 8px; padding: 4px 8px; }}
        """)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.PaletteChange and self._tokens is not theme.current():
            self._style()
        super().changeEvent(e)

    def set_recording(self, rec) -> None:
        """The recording whose items to show and change (Add adds to it)."""
        if rec is None or self.rec is None or rec.id != self.rec.id:
            self.editing, self.show_discarded = None, False
        self.rec = rec
        self.source = lambda: items_of(rec)
        self.set_items(self.source())

    def set_source(self, source) -> None:
        """Items from several recordings: `source()` returns them as saved now (each with its
        recording's id and its index there), discarded ones included."""
        self.rec, self.editing, self.show_discarded = None, None, False
        self.source = source
        self.set_items(source())

    def set_items(self, items: list[dict]) -> None:
        self.items = items
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)  # gone from the list at once, not when the event loop deletes it
                w.deleteLater()
        kept = [it for it in items if not it.get("discarded")]
        gone = [it for it in items if it.get("discarded")]
        if self.editing == ("", -1):
            self.lay.addWidget(self._editor(None))
        if not kept and self.editing != ("", -1):
            self.lay.addWidget(_dim(self.empty))
        for it in kept:
            self.lay.addWidget(self._editor(it) if self.editing == _key(it) else self._row(it))
        if gone and self.editable:
            n = len(gone)
            line = QHBoxLayout()
            line.addWidget(_dim(f"{n} discarded"))
            toggle = QPushButton("Hide" if self.show_discarded else "Show")
            toggle.setFlat(True)
            toggle.clicked.connect(self._toggle_discarded)
            line.addWidget(toggle)
            line.addStretch(1)
            holder = QWidget()
            holder.setLayout(line)
            line.setContentsMargins(0, 0, 0, 0)
            self.lay.addWidget(holder)
            if self.show_discarded:
                for it in gone:
                    self.lay.addWidget(self._row(it))
        self.relaid.emit()

    def start_add(self) -> None:
        if self.rec is not None:
            self.editing = ("", -1)
            self.set_items(self.items)

    def _toggle_discarded(self):
        self.show_discarded = not self.show_discarded
        self.set_items(self.items)

    def _rec_of(self, rid: str):
        if self.rec is not None and (not rid or rid == self.rec.id):
            return self.rec
        return self.library.get(rid) if self.library is not None and rid else None

    def _editor(self, it: dict | None) -> QWidget:
        rec = self._rec_of(it["id"] if it else "")
        names = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n] if rec is not None else []
        ed = ItemEditor(it, names)
        ed.saved.connect(lambda f, k=(_key(it) if it else None): self._save(k, f))
        ed.cancelled.connect(self._cancel)
        ed.text.setFocus()
        return ed

    def _row(self, it: dict) -> QWidget:
        row = QFrame()
        row.setObjectName("actionItem")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        gone, done = bool(it.get("discarded")), bool(it.get("done"))
        if gone:
            theme.set_role(row, discarded=True)
        elif done:
            theme.set_role(row, done=True)
        outer = QHBoxLayout(row)
        outer.setContentsMargins(12, 8, 6, 10)
        outer.setSpacing(10)
        if self.editable and not gone:
            check = QCheckBox()
            check.setChecked(done)
            check.setToolTip("Done" if not done else "Not done yet")
            check.setAccessibleName(f"Done: {it['text']}")
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.toggled.connect(lambda on, k=_key(it): self._done(k, on))
            outer.addWidget(check, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        outer.addLayout(col, 1)
        top = QHBoxLayout()
        top.setSpacing(2)
        text = QLabel(it["text"])
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f = theme.display_font(1.0, QFont.Weight.Bold)
        f.setStrikeOut(gone or done)
        text.setFont(f)
        if gone or done:
            theme.set_role(text, dim=True)
        top.addWidget(text, 1)
        state = it.get("state", actions.PROPOSED)
        if state == actions.SENT:
            top.addWidget(_sent_chip(it.get("tracker") or {}), 0, Qt.AlignmentFlag.AlignTop)
        elif self.editable and not gone:
            # Opt-in: an item goes to the tracker only once switched on here.
            send = Toggle(state == actions.READY, f"Send “{it['text']}” to your tracker", role="accent")
            send.toggled.connect(lambda on, k=_key(it): self._send(k, on))
            lbl = _dim("To tracker")
            lbl.setWordWrap(False)
            box = QHBoxLayout()
            box.setSpacing(6)
            box.addWidget(lbl)
            box.addWidget(send)
            top.addSpacing(8)
            top.addLayout(box)
            top.setAlignment(box, Qt.AlignmentFlag.AlignTop)
            top.addSpacing(4)
        elif state == actions.READY:
            top.addWidget(_chip("To send", "amber", "Chosen for your tracker; not sent yet"), 0,
                          Qt.AlignmentFlag.AlignTop)
        if self.editable and state != actions.SENT:  # a sent item is the tracker's
            if it.get("discarded"):
                restore = _small_button("undo-2", "Restore")
                restore.clicked.connect(lambda _c=False, k=_key(it): self._discard(k, False))
                top.addWidget(restore, 0, Qt.AlignmentFlag.AlignTop)
            else:
                edit = _small_button("pencil", "Edit")
                edit.clicked.connect(lambda _c=False, k=_key(it): self._edit(k))
                top.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)
                drop = _small_button("x", "Discard")
                drop.clicked.connect(lambda _c=False, k=_key(it): self._discard(k, True))
                top.addWidget(drop, 0, Qt.AlignmentFlag.AlignTop)
        col.addLayout(top)
        owner = "" if self.with_recording else it.get("owner")  # a person's page: theirs, all of them
        bits = [b for b in (owner, fmt_due(it["due"]) if it.get("due") else "",
                            f"{it['title']} · {fmt_date(it['created'])}" if self.with_recording else "",
                            "edited" if self.editable and it.get("edited") else "",
                            "added by you" if self.editable and it.get("origin") == "user" else "") if b]
        if bits or it.get("at") is not None:
            meta = QHBoxLayout()
            meta.setSpacing(8)
            meta.addWidget(_dim("  ·  ".join(bits)), 1)
            if it.get("at") is not None:
                b = _time_pill(float(it["at"]))
                b.clicked.connect(lambda _c=False, rid=it["id"], at=float(it["at"]): self.play.emit(rid, at))
                meta.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            col.addLayout(meta)
        if state == actions.FAILED and it.get("failure"):
            fail = QLabel(f"Could not be sent: {it['failure']}. Switch it on to send it again.")
            fail.setWordWrap(True)
            fail.setStyleSheet(f"color: {theme.current().coral_deep}; font-weight: 600;")
            col.addWidget(fail)
        if not self.compact and not gone and not done:  # a done item keeps to its line
            if it.get("description"):
                desc = QLabel(it["description"])
                desc.setWordWrap(True)
                desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                col.addWidget(desc)
            if it.get("context"):
                ctx = _dim(f"Context: {it['context']}")
                fc = ctx.font()
                fc.setItalic(True)
                ctx.setFont(fc)
                col.addWidget(ctx)
            if it.get("note"):
                note = QLabel(f"Your note: {it['note']}")
                note.setObjectName("actionNote")
                note.setWordWrap(True)
                col.addWidget(note)
        return row

    def _edit(self, k: tuple[str, int]):
        self.editing = k
        self.set_items(self.items)

    def _cancel(self):
        self.editing = None
        self.set_items(self.items)

    def _save(self, k: tuple[str, int] | None, fields: dict):
        rec = self._rec_of(k[0] if k else "")
        if rec is None:
            return
        if k is None:
            actions.add(rec, **fields)
        else:
            actions.update(rec, k[1], **fields)
        self.editing = None
        self._written()

    def _discard(self, k: tuple[str, int], on: bool):
        rec = self._rec_of(k[0])
        if rec is not None:
            actions.discard(rec, k[1], on)
            self._written()

    def _done(self, k: tuple[str, int], on: bool):
        rec = self._rec_of(k[0])
        if rec is not None:
            actions.set_done(rec, k[1], on)
            self._written()

    def _send(self, k: tuple[str, int], on: bool):
        rec = self._rec_of(k[0])
        if rec is not None:
            actions.set_send(rec, k[1], on)
            self._written()

    def _written(self):
        self.set_items(self.source())
        self.changed.emit()


def _chip(text: str, role: str, tip: str = "") -> QLabel:
    c = QLabel(text)
    c.setFont(theme.display_font(0.82, QFont.Weight.Bold))
    t = theme.current()
    fg = t.accent_deep if role == "accent" else t.ink
    c.setStyleSheet(f"color: {fg}; background: {theme.rgba(role, 0.2)}; border-radius: 9px; padding: 1px 8px;")
    if tip:
        c.setToolTip(tip)
    return c


def _sent_chip(tracker: dict) -> QLabel:
    """"✓ Sent · PROJ-123", a link to the item in the tracker when there is one."""
    ref = tracker.get("ref") or "sent"
    url = tracker.get("url") or ""
    c = _chip(f"✓ Sent · {ref}", "accent", f"In your tracker as {ref}" + (f": {url}" if url else ""))
    if url.startswith(("https://", "http://")):
        c.setText(f'<a href="{html.escape(url)}" style="color: {theme.current().accent_deep}; '
                  f'text-decoration: none;">✓ Sent · {html.escape(ref)}</a>')
        c.setOpenExternalLinks(True)
    return c


def _key(it: dict) -> tuple[str, int]:
    return (it["id"], it["index"])


def items_of(rec) -> list[dict]:
    d = actions.load(rec) if rec is not None else None
    return [{**it, "id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "index": k}
            for k, it in enumerate((d or {}).get("items", []))]


def person_section(library, name: str, show_recording) -> QWidget:
    """The items assigned to a person across the library, for their profile in People."""
    lst = ActionList(editable=True, with_recording=True, empty="No action items assigned to them.",
                     library=library)
    lst.set_source(lambda: actions.assigned_to(library, name, discarded=True))
    lst.play.connect(show_recording)
    return lst

"""Action items in the window: in a recording's Action items view, on the Action items page (every
meeting's open ones) and on a person's page, to polish, check off as done and choose for the team's
tracker; on a minutes card, at a glance.

A list works from the keyboard as well as the mouse (↑↓ to move, Space done, T tracker, E edit,
Delete discard, Ctrl+Z undo), and a check mark, a discard or a switch of every item can be taken
back from the bar that says what happened."""

from __future__ import annotations

import html
from datetime import date

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget)

from echo_app import export
from echo_app.library import fold_tag
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


UNDO_MS = 8000  # how long the bar offers to take a change back


def _small_button(ic: str, tip: str) -> QToolButton:
    b = QToolButton()
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the list keeps the keyboard
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
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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


class UndoBar(QFrame):
    """"Checked off “…”  Undo": the last change, to take back for a few seconds (or with Ctrl+Z)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("undoBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 6, 4)
        lay.setSpacing(8)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text, 1)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setFlat(True)
        self.undo_btn.setToolTip("Take it back (Ctrl+Z)")
        self.undo_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.undo_btn.clicked.connect(self.undo)
        lay.addWidget(self.undo_btn)
        self.fn = None
        self.timer = QTimer(self, singleShot=True, interval=UNDO_MS, timeout=self.dismiss)
        self._style()
        self.hide()

    def _style(self):
        # Its own style sheet: a host may lay it out away from the list.
        t = self._tokens = theme.current()
        self.setStyleSheet(f"""
            QFrame#undoBar {{ background: {t.ink}; border-radius: 10px; }}
            QFrame#undoBar QLabel {{ color: {t.canvas}; background: transparent; font-weight: 600; }}
            QFrame#undoBar QPushButton {{ color: {t.accent_soft}; background: transparent; border: none;
                font-weight: 800; padding: 4px 10px; }}
        """)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.PaletteChange and self._tokens is not theme.current():
            self._style()
        super().changeEvent(e)

    def offer(self, text: str, fn) -> None:
        self.text.setText(text)
        self.fn = fn
        self.show()
        self.timer.start()

    def undo(self) -> bool:
        fn, self.fn = self.fn, None
        self.dismiss()
        if fn is None:
            return False
        fn()
        return True

    def dismiss(self) -> None:
        self.timer.stop()
        self.fn = None
        self.hide()


class _Row(QFrame):
    """An item's card; a click makes it the list's current item."""

    def __init__(self, on_press):
        super().__init__()
        self.on_press = on_press

    def mousePressEvent(self, e):
        self.on_press()
        super().mousePressEvent(e)


class ActionList(QWidget):
    """Action items to work on: a recording's (its Action items view) or a person's across
    recordings, or every meeting's open ones (`grouped`, under a heading per meeting). Each can be
    checked off as done, switched on for the tracker, edited, given context or a note and
    discarded; done ones go to the end, folded into one line with Show, and discarded ones fold the
    same way with Restore. A recording's list can also be added to. `compact` leaves the
    description, context and note out. A time button plays where an item came up. `undo_bar` sits
    on top of the list unless the host puts it elsewhere (above its scroll area)."""

    play = Signal(str, float)  # recording id, seconds
    open_recording = Signal(str)  # a grouped list's heading
    changed = Signal()  # an actions.json was written
    relaid = Signal()  # rows or the editor changed, so the height may have

    def __init__(self, editable: bool = False, with_recording: bool = False, empty: str = "No action items.",
                 library=None, compact: bool = False, grouped: bool = False):
        super().__init__()
        self.setObjectName("actionList")
        self.editable = editable
        self.with_recording = with_recording
        self.grouped = grouped
        self.empty = empty
        self.library = library
        self.compact = compact
        self.rec = None
        self.source = lambda: []  # the items as saved now, discarded ones included
        self.items: list[dict] = []
        self.editing: tuple[str, int] | None = None  # (recording id, index); ("", -1) for a new item
        self.show_discarded = False
        self.show_done = False
        self.nav: list[tuple[tuple[str, int], QWidget]] = []  # the rows the keyboard moves through
        self.cur: int | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self.undo_bar = UndoBar()
        outer.addWidget(self.undo_bar)
        rows = QWidget()
        outer.addWidget(rows)
        self.lay = QVBoxLayout(rows)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)
        if editable:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            undo = QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo_bar.undo)
            undo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._style()

    def _style(self):
        t = self._tokens = theme.current()
        self.setStyleSheet(f"""
            QFrame#actionItem {{ background: {t.raised}; border: 1px solid {t.line}; border-radius: 12px; }}
            QFrame#actionItem[discarded="true"] {{ background: transparent; }}
            QFrame#actionItem[done="true"] {{ background: transparent; }}
            QFrame#actionItem[current="true"] {{ border: 2px solid {t.accent}; }}
            QPushButton#meetingHeading {{ border: none; background: transparent; color: {t.ink};
                text-align: left; padding: 10px 2px 2px 2px; }}
            QPushButton#meetingHeading:hover {{ color: {t.accent_deep}; }}
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
            self.editing, self.show_discarded, self.show_done, self.cur = None, False, False, None
            self.undo_bar.dismiss()
        self.rec = rec
        self.source = lambda: items_of(rec)
        self.set_items(self.source())

    def set_source(self, source) -> None:
        """Items from several recordings: `source()` returns them as saved now (each with its
        recording's id and its index there), discarded ones included."""
        self.rec, self.editing, self.show_discarded, self.show_done, self.cur = None, None, False, False, None
        self.source = source
        self.set_items(source())

    def set_items(self, items: list[dict]) -> None:
        self.items = items
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)  # gone from the list at once, not when the event loop deletes it
                w.deleteLater()
        self.nav = []
        kept = [it for it in items if not it.get("discarded")]
        todo = [it for it in kept if not it.get("done")]
        done = [it for it in kept if it.get("done")] if self.editable else []  # an editable list folds them
        if not self.editable:
            todo = kept
        gone = [it for it in items if it.get("discarded")]
        if self.editing == ("", -1):
            self.lay.addWidget(self._editor(None))
        if not kept and self.editing != ("", -1):
            self.lay.addWidget(_dim(self.empty))
        last = None
        for it in todo:
            if self.grouped and it["id"] != last:
                last = it["id"]
                self.lay.addWidget(self._heading(it))
            self._add(it)
        if done:
            self.lay.addWidget(self._fold(f"{len(done)} done", self.show_done, self._toggle_done))
            if self.show_done:
                for it in done:
                    self._add(it)
        if gone and self.editable:
            self.lay.addWidget(self._fold(f"{len(gone)} discarded", self.show_discarded, self._toggle_discarded))
            if self.show_discarded:
                for it in gone:
                    self._add(it)
        if self.cur is not None:
            self.cur = min(self.cur, len(self.nav) - 1) if self.nav else None
        self._mark_current()
        self.relaid.emit()

    def _add(self, it: dict) -> None:
        if self.editing == _key(it):
            self.lay.addWidget(self._editor(it))
            return
        k = len(self.nav)
        row = self._row(it, lambda k=k: self._set_current(k))
        self.nav.append((_key(it), row))
        self.lay.addWidget(row)

    def _fold(self, text: str, shown: bool, toggled) -> QWidget:
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(_dim(text))
        toggle = QPushButton("Hide" if shown else "Show")
        toggle.setFlat(True)
        toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toggle.clicked.connect(toggled)
        line.addWidget(toggle)
        line.addStretch(1)
        holder = QWidget()
        holder.setLayout(line)
        return holder

    def _heading(self, it: dict) -> QWidget:
        """A grouped list's meeting: its title and date, a click away from its Action items."""
        b = QPushButton(f"{it['title']}  ·  {fmt_date(it['created'])}")
        b.setObjectName("meetingHeading")
        b.setFlat(True)
        b.setFont(theme.display_font(1.05, QFont.Weight.ExtraBold))
        b.setToolTip("Open this meeting's action items")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(lambda _c=False, rid=it["id"]: self.open_recording.emit(rid))
        return b

    # ---- the keyboard ----

    def _set_current(self, k: int | None) -> None:
        if not self.nav or k is None:
            self.cur = None
        else:
            self.cur = max(0, min(k, len(self.nav) - 1))
        if self.editable:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._mark_current()

    def _mark_current(self) -> None:
        show = self.hasFocus()
        for k, (_key_, row) in enumerate(self.nav):
            on = show and k == self.cur
            if (row.property("current") == "true") != on:
                theme.set_role(row, current=on)
        if show and self.cur is not None:
            row = self.nav[self.cur][1]
            w = self.parentWidget()
            while w is not None and not isinstance(w, QScrollArea):
                w = w.parentWidget()
            if w is not None:
                QTimer.singleShot(0, lambda w=w, row=row: w.ensureWidgetVisible(row, 0, 24)
                                  if row.parent() is not None else None)

    def current(self) -> dict | None:
        if self.cur is None or not self.nav:
            return None
        k = self.nav[self.cur][0]
        return next((it for it in self.items if _key(it) == k), None)

    def focusInEvent(self, e):
        if self.cur is None and self.nav:
            self.cur = 0
        self._mark_current()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._mark_current()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        key, mods = e.key(), e.modifiers()
        it = self.current()
        if not self.editable or mods & ~Qt.KeyboardModifier.KeypadModifier:
            return super().keyPressEvent(e)
        if key in (Qt.Key.Key_Down, Qt.Key.Key_J):
            self._set_current(0 if self.cur is None else self.cur + 1)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_K):
            self._set_current(0 if self.cur is None else self.cur - 1)
        elif key == Qt.Key.Key_Home:
            self._set_current(0)
        elif key == Qt.Key.Key_End:
            self._set_current(len(self.nav) - 1)
        elif it is None:
            return super().keyPressEvent(e)
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_X) and not it.get("discarded"):
            self._done(_key(it), not it.get("done"))
        elif key == Qt.Key.Key_T and not it.get("discarded") and it.get("state") != actions.SENT:
            self._send(_key(it), it.get("state") != actions.READY)
        elif key in (Qt.Key.Key_E, Qt.Key.Key_Return, Qt.Key.Key_Enter) and it.get("state") != actions.SENT \
                and not it.get("discarded"):
            self._edit(_key(it))
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and it.get("state") != actions.SENT:
            self._discard(_key(it), not it.get("discarded"))
        else:
            return super().keyPressEvent(e)
        e.accept()

    def start_add(self) -> None:
        if self.rec is not None:
            self.editing = ("", -1)
            self.set_items(self.items)

    def _toggle_discarded(self):
        self.show_discarded = not self.show_discarded
        self.set_items(self.items)

    def _toggle_done(self):
        self.show_done = not self.show_done
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

    def _row(self, it: dict, on_press=lambda: None) -> QWidget:
        row = _Row(on_press)
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
            check.setToolTip("Not done yet: uncheck" if done else
                             "Check off when it is done. The mark is yours: Echo never dates items as late "
                             "or reminds you")
            check.setAccessibleName(f"Done: {it['text']}")
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
            tip = ("Off: stays in Echo. On: whatever sends your items (an agent or a script) picks it "
                   "up; once it is in your tracker it shows ✓ Sent with a link. Switch it off again "
                   "before then to keep it here.")
            send.setToolTip(tip)
            send.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            send.toggled.connect(lambda on, k=_key(it): self._send(k, on))
            lbl = _dim("To tracker")
            lbl.setWordWrap(False)
            lbl.setToolTip(tip)
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
                edit.setToolTip("Edit: the title, description, owner and date, context for whoever picks it "
                                "up, and a note only for you")
                edit.clicked.connect(lambda _c=False, k=_key(it): self._edit(k))
                top.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)
                drop = _small_button("x", "Discard")
                drop.setToolTip("Discard: out of the list and never sent; Show under the list restores it")
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
        if self.editable:
            self.setFocus()

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
        self.setFocus()

    def _discard(self, k: tuple[str, int], on: bool):
        rec = self._rec_of(k[0])
        if rec is not None:
            self._undoable(rec, [k[1]], f"Discarded “{self._text(k)}”" if on else "")
            actions.discard(rec, k[1], on)
            self._written()

    def _done(self, k: tuple[str, int], on: bool):
        rec = self._rec_of(k[0])
        if rec is not None:
            self._undoable(rec, [k[1]], f"Checked off “{self._text(k)}”" if on else "")
            actions.set_done(rec, k[1], on)
            self._written()

    def send_all(self, on: bool) -> int:
        """Every open item of the recording switched on for the tracker (or off), to take back."""
        rec = self.rec
        if rec is None:
            return 0
        snaps = [(it["index"], actions.snapshot(rec, it["index"])) for it in self.items
                 if not it.get("discarded") and not it.get("done") and it.get("state") != actions.SENT]
        n = actions.set_send_all(rec, on)
        if n:
            self._undoable(rec, [], f"Switched {n} item{'s' if n != 1 else ''} {'on' if on else 'off'} "
                                    "for your tracker", snaps)
        self._written()
        return n

    def _text(self, k: tuple[str, int]) -> str:
        it = next((i for i in self.items if _key(i) == k), None)
        t = (it or {}).get("text", "")
        return t if len(t) <= 48 else t[:47] + "…"

    def _undoable(self, rec, indexes: list[int], text: str, snaps=None) -> None:
        """Offer to put the items back as they are now (call before changing them); no text, no offer."""
        if not text:
            return
        snaps = snaps if snaps is not None else [(i, actions.snapshot(rec, i)) for i in indexes]

        def back():
            for i, snap in snaps:
                if snap is not None:
                    actions.restore(rec, i, snap)
            self._written()

        self.undo_bar.offer(text, back)

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


class ActionsScreen(QWidget):
    """The rail's Action items: every meeting's items not yet checked off, newest meeting first,
    under a heading per meeting, to work through without opening each call. Checked-off and
    discarded items leave the page (the bar offers to take that back); a meeting's own view still
    has them. The filter matches an item's words, its owner and its meeting's title."""

    def __init__(self, library, show_recording, open_actions, jobs=None):
        super().__init__()
        self.library = library
        self.setObjectName("content")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 20, 12)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(12)
        title = QLabel("Action items")
        title.setFont(theme.display_font(1.9, QFont.Weight.ExtraBold))
        head.addWidget(title)
        self.count = _dim()
        self.count.setWordWrap(False)
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by words, owner or meeting")
        self.filter.setClearButtonEnabled(True)
        self.filter.setAccessibleName("Filter action items")
        self.filter.setMaximumWidth(320)
        self.filter.textChanged.connect(lambda _t: self.reload())
        head.addWidget(self.filter, 1)
        lay.addLayout(head)
        self.list = ActionList(editable=True, library=library, grouped=True,
                               empty="Nothing left to do. Items from your meetings show here until you check "
                                     "them off.")
        self.list.play.connect(show_recording)
        self.list.open_recording.connect(open_actions)
        self.list.relaid.connect(self._count)
        lay.addWidget(self.list.undo_bar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        from .widgets import Opaque  # opaque, as in a meeting's view: smooth scrolling

        inner = Opaque("canvas")
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 8, 0)
        il.addWidget(self.list)
        il.addStretch(1)
        scroll.setWidget(inner)
        self.scroll = scroll
        lay.addWidget(scroll, 1)
        if jobs is not None:
            jobs.changed.connect(lambda _rid: self.reload() if self.isVisible() else None)
        self.list.set_source(self._items)

    def _items(self) -> list[dict]:
        q = fold_tag(self.filter.text().strip())
        items = actions.open_items(self.library)
        if not q:
            return items
        return [it for it in items if q in fold_tag(" ".join((it["text"], it.get("owner", ""), it["title"])))]

    def reload(self) -> None:
        if self.list.editing is None:  # never under the user's editor
            self.list.set_items(self.list.source())

    def _count(self):
        items = [it for it in self.list.items if not it.get("discarded") and not it.get("done")]
        meetings = len({it["id"] for it in items})
        self.count.setText("" if not items else
                           f"{len(items)} open in {meetings} meeting{'s' if meetings != 1 else ''}")

    def showEvent(self, e):
        self.reload()
        super().showEvent(e)

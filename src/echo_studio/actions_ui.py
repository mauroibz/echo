"""Action items in the window: in a recording's Action items view, on the Action items page (every
meeting's open ones) and on a person's page, to polish, check off as done and choose for the team's
tracker; on a minutes card, at a glance.

A list works from the keyboard as well as the mouse (↑↓ to move, Space done, T tracker, E edit,
Delete discard, Ctrl+Z undo), and a check mark, a discard or a switch of every item can be taken
back from the bar that says what happened."""

from __future__ import annotations

import html
from datetime import date

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from echo_app import export
from echo_app.library import fold_tag
from echo_app.ui import theme
from echo_app.ui.common import fmt_date, icon

from . import actions
from .widgets import AVATAR_ROLES, Avatar, AvatarStack, Hero, Opaque, Toggle, avatar_color


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


class RoundButton(QAbstractButton):
    """A round icon button: muted at rest, filled in `on_role` with a white icon when checked (the
    envelope lights up amber for the tracker, the check fills for done); `hover_role` tints it under
    the pointer (coral for discard)."""

    SIZE = 32

    def __init__(self, ic: str, tip: str, on_role: str = "accent", hover_role: str = "ink",
                 checkable: bool = True):
        super().__init__()
        self.ic, self.on_role, self.hover_role = ic, on_role, hover_role
        self.setCheckable(checkable)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.lit = False  # shown on without being a switch (a sent item's envelope)

    def sizeHint(self) -> QSize:
        return QSize(self.SIZE, self.SIZE)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        on, hover, live = self.isChecked() or self.lit, self.underMouse(), self.isEnabled()
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(self.on_role, 1.0 if live else 0.55))
            if live and self.on_role == "amber":  # lit: a soft halo
                p.setBrush(theme.color("amber", 0.25))
                p.drawEllipse(QRectF(self.rect()))
                p.setBrush(theme.color("amber"))
            p.drawEllipse(r)
            role = "on_accent" if self.on_role == "accent" else "ink"
            ico = theme.tinted(self.ic, role)
        else:
            if hover and live:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.color(self.hover_role, 0.16 if self.hover_role != "ink" else 0.07))
                p.drawEllipse(r)
            else:
                p.setPen(theme.color("ink", 0.16 if live else 0.07))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(r)
            role = (self.hover_role if hover and self.hover_role != "ink" else "ink") if live else "line"
            ico = theme.tinted(self.ic, role if hover or not live else "muted")
        x = (self.width() - 16) // 2
        ico.paint(p, x, x, 16, 16)  # sharp at any scale, unlike a 16 px pixmap
        p.end()


class ClickFrame(QFrame):
    """A frame that is a button: a meeting card's head."""

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class _Row(QFrame):
    """An item's card; a click makes it the list's current item. Nothing in it shows or hides on
    hover: a row passing under a still pointer while scrolling then cost 3.5 ms of layout (a
    scroll step costs 0.3), and that was the stutter."""

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
            QFrame#meetingCard {{ background: {t.surface}; border: 1px solid {t.line}; border-radius: 16px; }}
            QFrame#meetingHead {{ background: transparent; border: none; border-top-left-radius: 16px;
                border-top-right-radius: 16px; }}
            QFrame#meetingHead:hover {{ background: {t.raised}; }}
            QFrame#denseItem {{ background: transparent; border: none; border-top: 1px solid {t.line};
                border-radius: 0; }}
            QFrame#denseItem[first="true"] {{ border-top: 1px solid {t.line}; }}
            QFrame#denseItem:hover {{ background: {t.raised}; border-radius: 10px; }}
            QFrame#denseItem[current="true"] {{ background: {t.accent_soft}; border-radius: 10px; }}
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
        self._cards: dict[str, tuple[QWidget, QLabel, str]] = {}  # a grouped list's cards by recording
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
        if self.grouped:
            groups: dict[str, list[dict]] = {}
            for it in todo:
                groups.setdefault(it["id"], []).append(it)
            for its in groups.values():
                card, body = self._group(its)
                self.lay.addWidget(card)
                for k, it in enumerate(its):
                    self._add(it, body, first=k == 0)
        else:
            for it in todo:
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

    def _add(self, it: dict, into: QVBoxLayout | None = None, first: bool = True) -> None:
        into = into if into is not None else self.lay
        if self.editing == _key(it):
            into.addWidget(self._editor(it))
            return
        k = len(self.nav)
        press = lambda k=k: self._set_current(k)  # noqa: E731
        row = self._dense_row(it, press, first) if self.grouped else self._row(it, press)
        self.nav.append((_key(it), row))
        into.addWidget(row)

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

    def _group(self, its: list[dict]) -> tuple[QWidget, QVBoxLayout]:
        """A grouped list's meeting as a card: a date tile in the meeting's color, its title, who was
        there and how far its items are, a click away from its Action items; its rows go under."""
        it = its[0]
        rec = self._rec_of(it["id"])
        role = meeting_role(it["id"])
        t = theme.current()
        card = QFrame()
        card.setObjectName("meetingCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(0)
        head = ClickFrame()
        head.setObjectName("meetingHead")
        head.setToolTip("Open this meeting's action items")
        head.setAccessibleName(f"Open {it['title']}")
        head.clicked.connect(lambda rid=it["id"]: self.open_recording.emit(rid))
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 14, 18, 12)
        hl.setSpacing(14)
        hl.addWidget(DateTile(it["created"], role))
        col = QVBoxLayout()
        col.setSpacing(4)
        title = QLabel(it["title"])
        title.setFont(theme.display_font(1.15, QFont.Weight.ExtraBold))
        title.setStyleSheet(f"color: {t.ink}; background: transparent;")
        col.addWidget(title)
        sub = QHBoxLayout()
        sub.setSpacing(10)
        names = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n] if rec is not None else []
        if names:
            sub.addWidget(AvatarStack(names, 20, ring="surface", limit=4))
        saved = actions.load(rec) if rec is not None else None
        live = [i for i in (saved or {}).get("items", []) if not i["discarded"]]
        done = sum(1 for i in live if i["done"])
        when = _dim(_head_text(it["created"], live))
        when.setWordWrap(False)
        self._cards[it["id"]] = (card, when, it["created"])
        sub.addWidget(when, 0, Qt.AlignmentFlag.AlignVCenter)
        tags = [tg for tg in (rec.meta.tags if rec is not None else []) if not tg.lower().startswith("template:")]
        for tg in tags[:2]:
            sub.addWidget(_state_chip(f"#{tg}", "accent", ""), 0, Qt.AlignmentFlag.AlignVCenter)
        sub.addStretch(1)
        col.addLayout(sub)
        hl.addLayout(col, 1)
        go = QLabel()
        go.setPixmap(icon("arrow-right", "muted").pixmap(18, 18))
        go.setStyleSheet("background: transparent;")
        hl.addWidget(go, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(head)
        body = QVBoxLayout()
        body.setContentsMargins(8, 0, 8, 0)
        body.setSpacing(0)
        lay.addLayout(body)
        return card, body

    def _dense_row(self, it: dict, on_press, first: bool) -> QWidget:
        """An item on one or two lines: the check, the title, then chips for owner, date, the moment
        and the way to the tracker, and the description cut to one line (all of it in the tooltip)."""
        row = _Row(on_press)
        row.setObjectName("denseItem")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        theme.set_role(row, first=first)
        state = it.get("state", actions.PROPOSED)
        outer = QHBoxLayout(row)
        outer.setContentsMargins(16, 10, 10, 10)
        outer.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(6)
        text = QLabel(it["text"])
        text.setWordWrap(True)
        text.setFont(theme.display_font(1.0, QFont.Weight.Bold))
        text.setStyleSheet("background: transparent;")
        col.addWidget(text)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        owner = it.get("owner") or ""
        chips.addWidget(OwnerChip(owner) if owner else _meta_chip("users", "No owner", "muted"))
        if it.get("due"):
            chips.addWidget(_meta_chip("calendar", fmt_due(it["due"])[3:], "ink", "Due " + it["due"]))
        if it.get("at") is not None:
            b = _time_pill(float(it["at"]))
            b.clicked.connect(lambda _c=False, rid=it["id"], at=float(it["at"]): self.play.emit(rid, at))
            chips.addWidget(b)
        if it.get("note"):
            chips.addWidget(_meta_chip("sticky-note", "Note", "amber", f"Your note: {it['note']}"))
        if it.get("context"):
            chips.addWidget(_meta_chip("message-square-text", "Context", "muted", f"Context: {it['context']}"))
        if state == actions.READY:
            chips.addWidget(_state_chip("To send", "amber", "Switched on: waiting for whatever sends your items"))
        elif state == actions.SENT:
            chips.addWidget(_sent_chip(it.get("tracker") or {}))
        elif state == actions.FAILED:
            chips.addWidget(_state_chip("Not sent", "coral", f"Could not be sent: {it.get('failure', '')}. "
                                                       "Switch it on to send it again."))
        if it.get("origin") == "user":
            chips.addWidget(_meta_chip("pencil", "Added by you", "muted"))
        chips.addStretch(1)
        col.addLayout(chips)
        if it.get("description"):
            desc = Elided(it["description"])
            desc.setToolTip(it["description"])
            col.addWidget(desc)
        outer.addLayout(col, 1)
        # On the right, always in sight: edit, the tracker's envelope, done and discard.
        tools = QHBoxLayout()
        tools.setSpacing(4)
        sent = state == actions.SENT
        edit = RoundButton("pencil", "Edit the title, description, owner, date, context and your note (E)")
        edit.setAccessibleName("Edit")
        edit.setEnabled(not sent)
        edit.clicked.connect(lambda _c=False, k=_key(it): self._edit(k))
        tools.addWidget(edit)
        if sent:
            ref = (it.get("tracker") or {}).get("ref") or "your tracker"
            send = RoundButton("mail", f"Sent: in your tracker as {ref}", on_role="accent", checkable=False)
            send.lit = True  # stays lit, and still says where it went
            send.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            send = RoundButton("mail", "Send to your tracker (T). Lit: whatever sends your items picks it up; "
                                       "off: it stays in Echo", on_role="amber", hover_role="amber")
            send.setChecked(state == actions.READY)
            send.toggled.connect(lambda on, k=_key(it): self._send(k, on))
        send.setAccessibleName(f"Send to tracker: {it['text']}")
        tools.addWidget(send)
        done = RoundButton("check", "Done (Space): it leaves this page; Undo brings it back", on_role="accent",
                           hover_role="accent")
        done.setChecked(bool(it.get("done")))
        done.setAccessibleName(f"Done: {it['text']}")
        done.toggled.connect(lambda on, k=_key(it): self._done(k, on))
        tools.addWidget(done)
        drop = RoundButton("x", "Discard (Delete): never sent; the meeting's own view can restore it",
                           hover_role="coral", checkable=False)
        drop.setAccessibleName("Discard")
        drop.setEnabled(not sent)
        drop.clicked.connect(lambda _c=False, k=_key(it): self._discard(k, True))
        tools.addWidget(drop)
        outer.addLayout(tools)
        outer.setAlignment(tools, Qt.AlignmentFlag.AlignTop)
        return row

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
        new = self.source()
        if not self._patch(new):
            self.set_items(new)
        self.changed.emit()

    def _patch(self, new: list[dict]) -> bool:
        """A grouped list after a check mark, a discard or a switch: drop the rows that left and
        rebuild the ones that changed, instead of every row. With 180 items a check mark took
        0.4 s rebuilt and 15 ms patched. False when rows were added or moved (an undo): rebuild."""
        if not self.grouped or self.editing is not None:
            return False
        shown = [it for it in new if not it.get("discarded") and not it.get("done")]
        keys = [_key(it) for it in shown]
        old = [k for k, _row in self.nav]
        pos = {k: n for n, k in enumerate(old)}
        if not keys or any(k not in pos for k in keys) or [pos[k] for k in keys] != sorted(pos[k] for k in keys):
            return False
        before = {_key(it): it for it in self.items}
        rows = dict(self.nav)
        touched = set()
        for k in set(old) - set(keys):
            rows[k].setParent(None)
            rows[k].deleteLater()
            touched.add(k[0])
        nav = []
        now = {_key(it): it for it in shown}
        for n, k in enumerate(keys):
            row = rows[k]
            if now[k] != before.get(k):
                lay = row.parentWidget().layout()
                fresh = self._dense_row(now[k], lambda: None, row.property("first") == "true")
                lay.replaceWidget(row, fresh)
                row.setParent(None)
                row.deleteLater()
                row = fresh
                touched.add(k[0])
            row.on_press = lambda n=n: self._set_current(n)
            nav.append((k, row))
        for rid in touched:
            card, when, created = self._cards[rid]
            if not any(k[0] == rid for k in keys):
                card.setParent(None)
                card.deleteLater()
                del self._cards[rid]
                continue
            rec = self._rec_of(rid)
            live = [i for i in ((actions.load(rec) if rec is not None else None) or {}).get("items", [])
                    if not i["discarded"]]
            when.setText(_head_text(created, live))
        self.items, self.nav = new, nav
        if self.cur is not None:
            self.cur = min(self.cur, len(nav) - 1)
        self._mark_current()
        self.relaid.emit()
        return True


def _head_text(created: str, live: list[dict]) -> str:
    """A meeting card's line: when, and how many of its items are open and done (all of them,
    whatever the page's filter shows)."""
    done = sum(1 for i in live if i["done"])
    return "  ·  ".join([fmt_date(created), f"{len(live) - done} open"] + ([f"{done} done"] if done else []))


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


# ---- the Action items page ----

def meeting_role(rid: str) -> str:
    """A meeting's color, the same wherever it shows (its date tile, its progress)."""
    import hashlib

    return AVATAR_ROLES[int(hashlib.sha1(rid.encode()).hexdigest()[:4], 16) % len(AVATAR_ROLES)]


class DateTile(QWidget):
    """A meeting's day as a small calendar leaf in its color: the month above, the day under."""

    def __init__(self, iso: str, role: str):
        super().__init__()
        from datetime import datetime

        self.role = role
        try:
            d = datetime.fromisoformat(iso)
            self.month, self.day = f"{d:%b}".upper(), str(d.day)
        except (TypeError, ValueError):
            self.month, self.day = "", "?"
        self.setFixedSize(46, 50)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = theme.color(self.role)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 34))
        p.drawRoundedRect(r, 12, 12)
        top = QRectF(r.left(), r.top(), r.width(), 17)
        p.setBrush(c)
        p.drawRoundedRect(top, 12, 12)
        p.drawRect(QRectF(top.left(), top.top() + 9, top.width(), top.height() - 9))
        f = theme.display_font(0.68, QFont.Weight.ExtraBold)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(top, Qt.AlignmentFlag.AlignCenter, self.month)
        f = theme.display_font(1.35, QFont.Weight.ExtraBold, tabular=True)
        p.setFont(f)
        p.setPen(theme.color("ink"))
        p.drawText(QRectF(r.left(), top.bottom(), r.width(), r.bottom() - top.bottom()), Qt.AlignmentFlag.AlignCenter,
                   self.day)
        p.end()


class Elided(QWidget):
    """One line of text, cut with "…" to the width it gets, painted. As a QLabel that set its text
    on each resize it was cut 20 times per item while the page laid out, and each new text asked
    for another layout pass."""

    def __init__(self, text: str):
        super().__init__()
        self.full = " ".join(text.split())
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.fontMetrics().height() + 2)
        self.setAccessibleName(self.full)

    def text(self) -> str:
        return self.full

    def sizeHint(self) -> QSize:
        return QSize(200, self.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(40, self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setPen(theme.color("muted"))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight, self.width()))
        p.end()


class Chip(QWidget):
    """A small rounded tag, painted in one widget: an icon or an avatar, then the text. A frame with
    a style sheet and two labels inside cost 6x as much to build; with 180 items the page took
    0.8 s to show. Colors are read at paint time, so a theme change needs nothing more."""

    H = 22

    def __init__(self, text: str, fg: str = "ink", bg: str = "ink", alpha: float = 0.06, ic: str = "",
                 ic_role: str = "muted", avatar: str = "", tip: str = ""):
        super().__init__()
        self.text, self.fg, self.bg, self.alpha = text, fg, bg, alpha
        self.ic, self.ic_role, self.avatar = ic, ic_role, avatar
        self.font_ = theme.display_font(0.82, QFont.Weight.Bold)
        lead = 18 + 5 if avatar else (13 + 5 if ic else 0)
        self.lead = lead
        self._w = (2 if avatar else 7 if ic else 8) + lead + QFontMetrics(self.font_).horizontalAdvance(text) + 9
        self.setFixedSize(self._w, self.H)
        if tip:
            self.setToolTip(tip)
        self.setAccessibleName(text)

    def sizeHint(self) -> QSize:
        return QSize(self._w, self.H)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.avatar:
            c = avatar_color(self.avatar)
            c.setAlphaF(0.13)
            p.setBrush(c)
        else:
            p.setBrush(theme.color(self.bg, self.alpha))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        x = 2.0 if self.avatar else 7.0 if self.ic else 8.0
        if self.avatar:
            a = QRectF(x, 2, 18, 18)
            p.setBrush(avatar_color(self.avatar))
            p.drawEllipse(a)
            f = theme.display_font(0.6, QFont.Weight.ExtraBold)
            f.setPixelSize(7)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            from .widgets import initials

            p.drawText(a, Qt.AlignmentFlag.AlignCenter, initials(self.avatar))
            x += 18 + 5
        elif self.ic:
            theme.tinted(self.ic, self.ic_role).paint(p, int(x), (self.H - 13) // 2, 13, 13)
            x += 13 + 5
        p.setFont(self.font_)
        p.setPen(theme.color(self.fg))
        p.drawText(QRectF(x, 0, r.width() - x, r.height()), Qt.AlignmentFlag.AlignVCenter, self.text)
        p.end()


def _meta_chip(ic: str, text: str, role: str, tip: str = "") -> Chip:
    """A chip with an icon: a date, a note, who added it."""
    if role in ("muted", "ink"):
        return Chip(text, fg=role, ic=ic, tip=tip)
    return Chip(text, fg="ink", bg=role, alpha=0.16, ic=ic, ic_role=role, tip=tip)


def OwnerChip(name: str) -> Chip:  # noqa: N802 - a widget, named as one
    """Who does it: their avatar and name, tinted in their color."""
    return Chip(name, avatar=name, tip=f"Owner: {name}")


def _state_chip(text: str, role: str, tip: str) -> Chip:
    return Chip(text, fg="accent_deep" if role == "accent" else "ink", bg=role, alpha=0.2, tip=tip)


class StatTile(QPushButton):
    """A count in the page's band that is also its filter: Open, To send, Sent, No owner."""

    def __init__(self, key: str, caption: str, role: str):
        super().__init__()
        self.key, self.role = key, role
        self.setObjectName("statTile")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(124, 84)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(2)
        self.number = QLabel("0")
        self.number.setFont(theme.display_font(1.9, QFont.Weight.ExtraBold, tabular=True))
        lay.addWidget(self.number)
        cap = QLabel(caption.upper())
        cap.setFont(theme.display_font(0.72, QFont.Weight.ExtraBold))
        theme.set_role(cap, eyebrow=True)
        lay.addWidget(cap)
        self.setAccessibleName(caption)

    def set_count(self, n: int) -> None:
        self.number.setText(str(n))


VIEWS = {  # a stat tile's filter
    "open": lambda it: True,
    "ready": lambda it: it.get("state") in (actions.READY, actions.FAILED),
    "sent": lambda it: it.get("state") == actions.SENT,
    "unowned": lambda it: not (it.get("owner") or "").strip(),
}


class ActionsScreen(QWidget):
    """The rail's Action items: every meeting's items not yet checked off, newest meeting first,
    one card per meeting, to work through without opening each call. The band counts them and its
    tiles filter (open, to send, sent, without an owner); the owners' chips and the search narrow
    further. Checked-off and discarded items leave the page (the bar at the bottom offers to take
    that back); a meeting's own view still has them."""

    def __init__(self, library, show_recording, open_actions, jobs=None):
        super().__init__()
        self.library = library
        self.view = "open"
        self.owner: str | None = None
        self.setObjectName("content")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = Opaque("canvas")  # opaque, as in a meeting's view: smooth scrolling
        body.setObjectName("content")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        scroll.setWidget(body)
        self.scroll = scroll
        outer.addWidget(scroll, 1)

        # The band: what there is to do, in numbers that filter.
        self.hero = Hero()
        hl = QHBoxLayout(self.hero)
        hl.setContentsMargins(44, 28, 44, Hero.WAVE_H + 22)
        hl.setSpacing(24)
        words = QVBoxLayout()
        words.setSpacing(4)
        self.eyebrow = QLabel()
        self.eyebrow.setFont(theme.display_font(0.82, QFont.Weight.ExtraBold))
        theme.set_role(self.eyebrow, eyebrow=True)
        words.addWidget(self.eyebrow)
        title = QLabel("Action items")
        title.setFont(theme.display_font(2.3, QFont.Weight.ExtraBold))
        words.addWidget(title)
        words.addStretch(1)
        hl.addLayout(words, 1)
        self.tiles: dict[str, StatTile] = {}
        for key, caption, role in (("open", "Open", "on_deep"), ("ready", "To send", "amber"),
                                   ("sent", "In tracker", "foam"), ("unowned", "No owner", "coral")):
            tile = StatTile(key, caption, role)
            tile.clicked.connect(lambda _c=False, k=key: self._set_view(k))
            self.tiles[key] = tile
            hl.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        self._style_tiles()
        bl.addWidget(self.hero)

        # Under it: who, and a search.
        page = QHBoxLayout()
        page.setContentsMargins(36, 0, 36, 32)
        page.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(MAX_PAGE_W)
        cl = QVBoxLayout(column)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(14)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.owners_row = QHBoxLayout()
        self.owners_row.setSpacing(6)
        bar.addLayout(self.owners_row)
        bar.addStretch(1)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search items, owners, meetings")
        self.filter.setClearButtonEnabled(True)
        self.filter.setAccessibleName("Filter action items")
        self.filter.addAction(icon("search", "muted"), QLineEdit.ActionPosition.LeadingPosition)
        self.filter.setMinimumWidth(240)
        self.filter.setMaximumWidth(320)
        # Filtered once typing pauses: each pass rebuilds the cards.
        self._typed = QTimer(self, singleShot=True, interval=150, timeout=self.reload)
        self.filter.textChanged.connect(lambda _t: self._typed.start())
        bar.addWidget(self.filter)
        cl.addLayout(bar)
        self.list = ActionList(editable=True, library=library, grouped=True, empty="")
        self.list.lay.setSpacing(14)
        self.list.play.connect(show_recording)
        self.list.open_recording.connect(open_actions)
        self.list.relaid.connect(self._count)
        cl.addWidget(self.list)
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setContentsMargins(0, 40, 0, 40)
        el.setSpacing(6)
        art = QLabel()
        art.setPixmap(icon("circle-check", "accent").pixmap(44, 44))
        el.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)
        self.empty_title = QLabel("All clear")
        self.empty_title.setFont(theme.display_font(1.4, QFont.Weight.ExtraBold))
        el.addWidget(self.empty_title, 0, Qt.AlignmentFlag.AlignHCenter)
        self.empty_text = _dim("Items from your meetings show here until you check them off.")
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        el.addWidget(self.empty_text)
        cl.addWidget(self.empty)
        page.addWidget(column, 100)
        page.addStretch(1)
        bl.addLayout(page)
        bl.addStretch(1)

        # The undo bar floats at the bottom, in sight wherever the page is scrolled.
        foot = QHBoxLayout()
        foot.setContentsMargins(36, 0, 36, 14)
        foot.addStretch(1)
        self.list.undo_bar.setMaximumWidth(MAX_PAGE_W)
        foot.addWidget(self.list.undo_bar, 100)
        foot.addStretch(1)
        outer.addLayout(foot)
        if jobs is not None:
            jobs.changed.connect(lambda _rid: self.reload() if self.isVisible() else None)
        self.all: list[dict] = []
        self.list.source = self._items  # built when first shown, not while the window starts

    def _style_tiles(self):
        t = self._tokens = theme.current()
        for tile in self.tiles.values():
            c = getattr(t, tile.role)
            tile.setStyleSheet(f"""
                QPushButton#statTile {{ background: {theme.rgba('deep_top', 0.62)};
                    border: 1px solid {theme.rgba('on_deep', 0.16)}; border-radius: 16px; text-align: left; }}
                QPushButton#statTile:hover {{ background: {theme.rgba('deep_top', 0.8)}; }}
                QPushButton#statTile:checked {{ background: {theme.rgba('deep_top', 0.85)}; border: 2px solid {c}; }}
                QPushButton#statTile QLabel {{ background: transparent; color: {t.on_deep}; }}
                QPushButton#statTile QLabel[eyebrow="true"] {{ color: {c}; letter-spacing: 1.2px; }}
            """)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.PaletteChange and getattr(self, "_tokens", None) is not theme.current():
            self._style_tiles()
            self.reload()
        super().changeEvent(e)

    def _items(self) -> list[dict]:
        self.all = actions.open_items(self.library)
        q = fold_tag(self.filter.text().strip())
        keep = VIEWS[self.view]
        own = fold_tag(self.owner) if self.owner else None
        return [it for it in self.all if keep(it)
                and (own is None or fold_tag(it.get("owner") or "") == own)
                and (not q or q in fold_tag(" ".join((it["text"], it.get("owner", ""), it["title"],
                                                      it.get("description", ""))))) ]

    def _set_view(self, key: str) -> None:
        self.view = key if key != self.view else "open"
        self.reload()

    def _set_owner(self, name: str | None) -> None:
        self.owner = None if name is None or (self.owner and fold_tag(self.owner) == fold_tag(name)) else name
        self.reload()

    def reload(self) -> None:
        if self.list.editing is not None:  # never under the user's editor
            return
        items = self.list.source()
        if items == self.list.items and self.list.nav:  # unchanged: coming back to the page costs nothing
            self._count()
            return
        self.list.set_items(items)

    def _count(self):
        every = self.all
        meetings = len({it["id"] for it in every})
        self.eyebrow.setText(f"ACROSS {meetings} MEETING{'S' if meetings != 1 else ''}" if every else "NOTHING OPEN")
        for key, tile in self.tiles.items():
            tile.set_count(sum(1 for it in every if VIEWS[key](it)))
            tile.setChecked(key == self.view)
        self._owners(every)
        shown = bool(self.list.items)
        self.list.setVisible(shown)
        self.empty.setVisible(not shown)
        filtered = self.view != "open" or self.owner or self.filter.text().strip()
        self.empty_title.setText("Nothing matches" if every and filtered else "All clear")
        self.empty_text.setText("Try another filter, or clear the search." if every and filtered else
                                "Items from your meetings show here until you check them off.")

    def _owners(self, every: list[dict]) -> None:
        """A chip per owner, most items first, to show only theirs."""
        while self.owners_row.count():
            w = self.owners_row.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        counts: dict[str, tuple[str, int]] = {}
        for it in every:
            o = (it.get("owner") or "").strip()
            if o:
                name, n = counts.get(fold_tag(o), (o, 0))
                counts[fold_tag(o)] = (name, n + 1)
        for name, n in sorted(counts.values(), key=lambda v: (-v[1], v[0].lower()))[:OWNER_CHIPS]:
            b = QPushButton(f"{name.split()[0]}  {n}")
            b.setObjectName("ownerFilter")
            b.setIcon(_avatar_icon(name))
            b.setIconSize(QSize(22, 22))
            b.setCheckable(True)
            b.setChecked(bool(self.owner) and fold_tag(self.owner) == fold_tag(name))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(f"Only {name}'s items")
            t = theme.current()
            b.setStyleSheet(f"""
                QPushButton#ownerFilter {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line};
                    border-radius: 15px; padding: 4px 11px 4px 5px; font-weight: 700; }}
                QPushButton#ownerFilter:hover {{ background: {t.raised}; }}
                QPushButton#ownerFilter:checked {{ background: {t.accent_soft}; border: 1px solid {t.accent}; }}
            """)
            b.clicked.connect(lambda _c=False, nm=name: self._set_owner(nm))
            self.owners_row.addWidget(b)

    def showEvent(self, e):
        self.reload()
        super().showEvent(e)


MAX_PAGE_W = 980  # the page's column: lines short enough to read across a wide window
OWNER_CHIPS = 6


def _avatar_icon(name: str):
    from PySide6.QtGui import QIcon, QPixmap

    pm = QPixmap(44, 44)
    pm.fill(Qt.GlobalColor.transparent)
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QRegion

    Avatar(name, 44).render(pm, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)  # no background
    return QIcon(pm)

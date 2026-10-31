"""Action items in the window: under a summary, to polish, and in a person's profile, to read."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from echo_app import export
from echo_app.ui import theme
from echo_app.ui.common import fmt_date, icon

from . import actions


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
    """An item's fields: text, owner (one of the recording's speakers, or typed), due date, context."""

    saved = Signal(dict)
    cancelled = Signal()

    def __init__(self, it: dict | None, names: list[str]):
        super().__init__()
        it = it or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(6)
        self.text = QLineEdit(it.get("text", ""))
        self.text.setPlaceholderText("What has to be done")
        self.text.setAccessibleName("Action item")
        lay.addWidget(self.text)
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
        self.context = QPlainTextEdit(it.get("context", ""))
        self.context.setPlaceholderText("Context for whoever picks it up")
        self.context.setAccessibleName("Context")
        self.context.setFixedHeight(self.context.fontMetrics().lineSpacing() * 3 + 14)
        lay.addWidget(self.context)
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
            self.saved.emit({"text": self.text.text(), "owner": self.owner.currentText(),
                             "due": self.due.text().strip(), "context": self.context.toPlainText()})


class ActionList(QWidget):
    """A recording's items, or a person's across recordings. Editable (under a summary): each item can
    be edited, given context and discarded; discarded ones fold into one line with Restore; items can
    be added. Read-only (in a profile): each item with its recording. A time button plays where an
    item came up."""

    play = Signal(str, float)  # recording id, seconds
    changed = Signal()  # the recording's actions.json was written
    relaid = Signal()  # rows or the editor changed, so the height may have

    def __init__(self, editable: bool = False, with_recording: bool = False, empty: str = "No action items."):
        super().__init__()
        self.editable = editable
        self.with_recording = with_recording
        self.empty = empty
        self.rec = None
        self.names: list[str] = []
        self.items: list[dict] = []
        self.editing: int | None = None  # index in actions.json; -1 for a new item
        self.show_discarded = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)

    def set_recording(self, rec) -> None:
        """Editable mode: the recording whose items to show and change."""
        if rec is None or self.rec is None or rec.id != self.rec.id:
            self.editing, self.show_discarded = None, False
        self.rec = rec
        self.names = [n for n in dict.fromkeys(rec.meta.speakers.values()) if n] if rec is not None else []
        self.set_items(items_of(rec))

    def set_items(self, items: list[dict]) -> None:
        self.items = items
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)  # gone from the list at once, not when the event loop deletes it
                w.deleteLater()
        kept = [it for it in items if not it.get("discarded")]
        gone = [it for it in items if it.get("discarded")]
        if self.editing == -1:
            self.lay.addWidget(self._editor(None))
        if not kept and self.editing != -1:
            self.lay.addWidget(_dim(self.empty))
        for it in kept:
            self.lay.addWidget(self._editor(it) if self.editing == it["index"] else self._row(it))
        if gone:
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
        self.editing = -1
        self.set_items(self.items)

    def _toggle_discarded(self):
        self.show_discarded = not self.show_discarded
        self.set_items(self.items)

    def _editor(self, it: dict | None) -> QWidget:
        ed = ItemEditor(it, self.names)
        ed.saved.connect(lambda f, k=(it["index"] if it else None): self._save(k, f))
        ed.cancelled.connect(self._cancel)
        ed.text.setFocus()
        return ed

    def _row(self, it: dict) -> QWidget:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(1)
        text = QLabel(it["text"])
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f = text.font()
        f.setWeight(QFont.Weight.DemiBold)
        f.setStrikeOut(bool(it.get("discarded")))
        text.setFont(f)
        if it.get("discarded"):
            theme.set_role(text, dim=True)
        col.addWidget(text)
        bits = [b for b in (it.get("owner"), fmt_due(it["due"]) if it.get("due") else "",
                            f"{it['title']} · {fmt_date(it['created'])}" if self.with_recording else "",
                            "edited" if self.editable and it.get("edited") else "",
                            "added by you" if self.editable and it.get("origin") == "user" else "") if b]
        if bits:
            col.addWidget(_dim("  ·  ".join(bits)))
        if it.get("context"):
            ctx = _dim(it["context"])
            fc = ctx.font()
            fc.setItalic(True)
            ctx.setFont(fc)
            col.addWidget(ctx)
        rl.addLayout(col, 1)
        if it.get("at") is not None:
            b = _time_pill(float(it["at"]))
            b.clicked.connect(lambda _c=False, rid=it["id"], at=float(it["at"]): self.play.emit(rid, at))
            rl.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        if self.editable:
            if it.get("discarded"):
                restore = _small_button("undo-2", "Restore")
                restore.clicked.connect(lambda _c=False, k=it["index"]: self._discard(k, False))
                rl.addWidget(restore, 0, Qt.AlignmentFlag.AlignTop)
            else:
                edit = _small_button("pencil", "Edit")
                edit.clicked.connect(lambda _c=False, k=it["index"]: self._edit(k))
                rl.addWidget(edit, 0, Qt.AlignmentFlag.AlignTop)
                drop = _small_button("x", "Discard")
                drop.clicked.connect(lambda _c=False, k=it["index"]: self._discard(k, True))
                rl.addWidget(drop, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _edit(self, index: int):
        self.editing = index
        self.set_items(self.items)

    def _cancel(self):
        self.editing = None
        self.set_items(self.items)

    def _save(self, index: int | None, fields: dict):
        if self.rec is None:
            return
        if index is None:
            actions.add(self.rec, **fields)
        else:
            actions.update(self.rec, index, **fields)
        self.editing = None
        self._written()

    def _discard(self, index: int, on: bool):
        if self.rec is not None:
            actions.discard(self.rec, index, on)
            self._written()

    def _written(self):
        self.set_items(items_of(self.rec))
        self.changed.emit()


def items_of(rec) -> list[dict]:
    d = actions.load(rec) if rec is not None else None
    return [{**it, "id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "index": k}
            for k, it in enumerate((d or {}).get("items", []))]


def person_section(library, name: str, show_recording) -> QWidget:
    """The items assigned to a person across the library, for their profile in People."""
    lst = ActionList(with_recording=True, empty="No action items assigned to them.")
    lst.set_items(actions.assigned_to(library, name))
    lst.play.connect(show_recording)
    return lst

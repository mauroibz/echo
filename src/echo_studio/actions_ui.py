"""Action items in the window: under a summary, across the library (Pending), and in a profile."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QToolButton, QVBoxLayout, QWidget)

from echo_app import export
from echo_app.index import Index
from echo_app.library import fold_tag
from echo_app.ui import theme
from echo_app.ui.common import fmt_date, icon

from . import actions


def _dim(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    theme.set_role(lbl, dim=True)
    return lbl


class ActionList(QWidget):
    """Items as checkboxes, each with its owner, due date and a button that plays where it came up."""

    toggled = Signal(str, int, bool)  # recording id, index in its actions.json, done
    play = Signal(str, float)  # recording id, seconds

    def __init__(self, with_recording: bool = False, empty: str = "No action items."):
        super().__init__()
        self.with_recording = with_recording
        self.empty = empty
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(6)

    def set_items(self, items: list[dict]) -> None:
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if not items:
            self.lay.addWidget(_dim(self.empty))
            return
        for it in items:
            self.lay.addWidget(self._row(it))

    def _row(self, it: dict) -> QWidget:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(0)
        box = QCheckBox(it["text"])
        box.setChecked(bool(it.get("done")))
        box.toggled.connect(lambda on, rid=it["id"], k=it["index"]: self.toggled.emit(rid, k, on))
        col.addWidget(box)
        bits = [b for b in (it.get("owner"), f"by {fmt_date(it['due'])}" if it.get("due") else "",
                            f"{it['title']} · {fmt_date(it['created'])}" if self.with_recording else "") if b]
        if bits:
            meta = _dim("  ·  ".join(bits))
            meta.setContentsMargins(26, 0, 0, 0)  # under the text, past the box
            col.addWidget(meta)
        rl.addLayout(col, 1)
        if it.get("at") is not None:
            b = QToolButton()
            b.setText(export.stamp(it["at"]))
            b.setIcon(icon("play"))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setToolTip("Play where this came up")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, rid=it["id"], at=float(it["at"]): self.play.emit(rid, at))
            rl.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        return row


def items_of(rec) -> list[dict]:
    d = actions.load(rec) if rec is not None else None
    return [{**it, "id": rec.id, "title": rec.meta.title, "created": rec.meta.created, "index": k}
            for k, it in enumerate((d or {}).get("items", []))]


class PendingScreen(QWidget):
    """Open items across the library, newest first, by person and tag."""

    def __init__(self, library, show_recording):
        super().__init__()
        self.library = library
        self.setObjectName("content")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 24, 18)
        lay.setSpacing(12)
        title = QLabel("Pending")
        title.setFont(theme.display_font(1.6, QFont.Weight.Bold))
        lay.addWidget(title)
        bar = QHBoxLayout()
        self.person = QComboBox()
        self.person.setAccessibleName("Person")
        self.person.currentIndexChanged.connect(lambda _i: self.refresh())
        bar.addWidget(self.person)
        self.tag = QLineEdit()
        self.tag.setPlaceholderText("#tag")
        self.tag.setAccessibleName("Tag")
        self.tag.setClearButtonEnabled(True)
        self.tag.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.tag, 1)
        lay.addLayout(bar)
        self.count = _dim()
        lay.addWidget(self.count)
        self.list = ActionList(with_recording=True, empty="Nothing open. Action items come from summaries.")
        self.list.toggled.connect(self._toggle)
        self.list.play.connect(show_recording)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 8, 0)
        hl.addWidget(self.list)
        hl.addStretch(1)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    def refresh(self) -> None:
        tags = [t.lstrip("#") for t in self.tag.text().split() if t.lstrip("#")]
        idx = Index(self.library) if tags else None
        try:
            if idx is not None:
                idx.sync()
            everyone = actions.open_items(self.library)
            items = actions.open_items(self.library, idx, self.person.currentData() or "", tags)
        finally:
            if idx is not None:
                idx.close()
        owners = sorted({i["owner"] for i in everyone if i.get("owner")}, key=fold_tag)
        keep = self.person.currentData()
        self.person.blockSignals(True)
        self.person.clear()
        self.person.addItem("Everyone", "")
        for o in owners:
            self.person.addItem(o, o)
        self.person.setCurrentIndex(max(0, self.person.findData(keep)) if keep else 0)
        self.person.blockSignals(False)
        self.count.setText(f"{len(items)} open item{'s' if len(items) != 1 else ''}")
        self.list.set_items(items)

    def _toggle(self, rid: str, index: int, done: bool):
        rec = self.library.get(rid)
        if rec is not None:
            actions.set_done(rec, index, done)


def person_section(library, name: str, show_recording) -> QWidget:
    """A person's open items, for their profile in People."""
    lst = ActionList(with_recording=True, empty="Nothing open.")
    lst.set_items(actions.open_items(library, person=name))

    def toggle(rid, index, done):
        rec = library.get(rid)
        if rec is not None:
            actions.set_done(rec, index, done)

    lst.toggled.connect(toggle)
    lst.play.connect(show_recording)
    return lst

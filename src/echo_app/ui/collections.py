"""Collections in the sidebar: the rows that open one, and the question asked when a batch is dropped."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .. import collections
from . import theme
from .common import icon
from .dialogs import FittedDialog, _dim, _heading
from .library_view import LibraryModel

ROW_H = 32
ROWS_SHOWN = 6  # more than this scroll: the list of recordings keeps most of the sidebar


class CollectionRow(QAbstractButton):
    """One place to look in: the day-to-day recordings (name None) or a collection. Shows how many
    it holds, as "7/15" while some are not transcribed yet. Files and recordings can be dropped on it."""

    files_dropped = Signal(object, list)  # name, [Path]
    recordings_dropped = Signal(object, list)  # name, [recording or set id]
    menu_requested = Signal(str, object)  # name, global position

    def __init__(self, name: str | None, parent=None):
        super().__init__(parent)
        self.name = name
        self.icon = ""  # the user's symbol for it ("hospital:coral"), in place of the folder
        self.count, self.done = 0, 0
        self._over = False
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.set_counts(0, 0)

    def title(self) -> str:
        return "Recordings" if self.name is None else self.name

    def set_counts(self, count: int, done: int):
        self.count, self.done = count, done
        self.setAccessibleName(f"{self.title()}, {count}")
        if self.name is None:
            self.setToolTip("Your day-to-day recordings: everything not filed in a collection")
        elif done < count:
            self.setToolTip(f"{self.name}: {done} of {count} transcribed")
        else:
            self.setToolTip(f"{self.name}: {count} recording{'s' if count != 1 else ''}")
        self.update()

    def badge(self) -> str:
        return f"{self.done}/{self.count}" if self.name is not None and self.done < self.count else str(self.count)

    def sizeHint(self) -> QSize:
        return QSize(200, ROW_H)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 1.5, -0.5, -1.5)
        if self._over:
            p.setPen(theme.color("foam"))
            p.setBrush(theme.color("foam", 0.22))
            p.drawRoundedRect(r, 8, 8)
        elif self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("foam", 0.20))
            p.drawRoundedRect(r, 8, 8)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("on_deep", 0.08))
            p.drawRoundedRect(r, 8, 8)
        role = "foam" if self.isChecked() else "on_deep"
        name, color = collections.icon_parts(self.icon)
        icon(name or ("audio-lines" if self.name is None else "folder"), color or role).paint(
            p, 10, (self.height() - 16) // 2, 16, 16)
        badge = self.badge()
        f = theme.display_font(0.85, QFont.Weight.DemiBold, tabular=True)
        p.setFont(f)
        bw = p.fontMetrics().horizontalAdvance(badge)
        p.setPen(theme.color("on_deep_muted"))
        p.drawText(QRectF(self.width() - bw - 12, 0, bw, self.height()), Qt.AlignmentFlag.AlignVCenter, badge)
        f = theme.display_font(0.95, QFont.Weight.Bold if self.isChecked() else QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(theme.color(role))
        room = self.width() - 34 - bw - 22
        text = p.fontMetrics().elidedText(self.title(), Qt.TextElideMode.ElideRight, max(room, 20))
        p.drawText(QRectF(34, 0, room, self.height()), Qt.AlignmentFlag.AlignVCenter, text)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def contextMenuEvent(self, e):
        if self.name is not None:
            self.menu_requested.emit(self.name, e.globalPos())

    # ---- drops: files to import here, recordings to file here ----
    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() or md.hasFormat(LibraryModel.MIME):
            e.acceptProposedAction()
            self._over = True
            self.update()

    def dragLeaveEvent(self, e):
        self._over = False
        self.update()

    def dropEvent(self, e):
        self._over = False
        self.update()
        md = e.mimeData()
        if md.hasFormat(LibraryModel.MIME):
            ids = [i for i in bytes(md.data(LibraryModel.MIME)).decode().split("\n") if i]
            e.acceptProposedAction()
            self.recordings_dropped.emit(self.name, ids)
        elif md.hasUrls():
            paths = [Path(u.toLocalFile()) for u in md.urls() if u.isLocalFile()]
            if paths:
                e.acceptProposedAction()
                self.files_dropped.emit(self.name, paths)


class CollectionBar(QWidget):
    """Where to look, above the list: Recordings (the day to day) and each collection. Hidden
    until there is a collection, so a library without any looks as it always did."""

    opened = Signal(object)  # a collection's name, or None for the day-to-day recordings
    files_dropped = Signal(object, list)
    recordings_dropped = Signal(object, list)
    menu_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        inner = QWidget()
        self.rows_lay = QVBoxLayout(inner)
        self.rows_lay.setContentsMargins(0, 0, 0, 0)
        self.rows_lay.setSpacing(0)
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll)
        self.rows: list[CollectionRow] = []
        self._open: str | None = None
        self.hide()

    def row(self, name: str | None) -> CollectionRow | None:
        return next((r for r in self.rows if (r.name is None) == (name is None)
                     and (name is None or collections.same(r.name, name))), None)

    def set_items(self, daily: int, items: list[collections.Collection]):
        """The day-to-day count and the collections; rows are rebuilt only when the names change."""
        names = [None, *(c.name for c in items)]
        if names != [r.name for r in self.rows]:
            for r in self.rows:
                self.rows_lay.removeWidget(r)
                r.deleteLater()
            self.rows = []
            for name in names:
                r = CollectionRow(name)
                r.clicked.connect(lambda _c=False, n=name: self.opened.emit(n))
                r.files_dropped.connect(self.files_dropped)
                r.recordings_dropped.connect(self.recordings_dropped)
                r.menu_requested.connect(self.menu_requested)
                self.rows_lay.addWidget(r)
                self.rows.append(r)
            self.scroll.setFixedHeight(ROW_H * min(len(self.rows), ROWS_SHOWN))
            self.set_open(self._open)
        self.rows[0].set_counts(daily, daily)
        for r, c in zip(self.rows[1:], items):
            r.icon = c.icon
            r.set_counts(len(c.recordings), c.transcribed)
        self.setVisible(bool(items))

    def set_open(self, name: str | None):
        self._open = name
        r = self.row(name)
        if r is not None:
            r.setChecked(True)


class IconPicker(QDialog):
    """A symbol and a color for a recording or a collection. Pick the color, then the symbol: the
    click on a symbol is the answer, in `icon` ("" for none)."""

    COLUMNS = 8

    def __init__(self, what: str, current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Icon")
        self.icon = collections.clean_icon(current)
        self.symbol, self.color = collections.icon_parts(self.icon)
        lay = QVBoxLayout(self)
        lay.addWidget(_heading(f"Icon for {what}", 1.1))
        # The symbols sit on the sidebar's color, as they will in the list.
        self.board = QFrame()
        self.board.setObjectName("iconboard")
        bl = QVBoxLayout(self.board)
        bl.setContentsMargins(10, 10, 10, 10)
        colors = QHBoxLayout()
        colors.setSpacing(6)
        self.swatches: dict[str, QToolButton] = {}
        for role in collections.COLORS:
            b = QToolButton()
            b.setObjectName("swatch")
            b.setFixedSize(26, 26)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setChecked(role == self.color)
            b.setToolTip("The text's color" if not role else role.capitalize())
            b.setAccessibleName(b.toolTip())
            b.clicked.connect(lambda _c=False, r=role: self._set_color(r))
            colors.addWidget(b)
            self.swatches[role] = b
        colors.addStretch(1)
        bl.addLayout(colors)
        grid = QGridLayout()
        grid.setSpacing(2)
        self.buttons: dict[str, QToolButton] = {}
        for k, name in enumerate(collections.ICONS):
            b = QToolButton()
            b.setObjectName("symbol")
            b.setFixedSize(38, 38)
            b.setIconSize(QSize(20, 20))
            b.setCheckable(True)
            b.setChecked(name == self.symbol)
            b.setToolTip(name.replace("-", " "))
            b.setAccessibleName(b.toolTip())
            b.clicked.connect(lambda _c=False, n=name: self._finish(n))
            grid.addWidget(b, k // self.COLUMNS, k % self.COLUMNS)
            self.buttons[name] = b
        bl.addLayout(grid)
        lay.addWidget(self.board)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.none_btn = bb.addButton("No icon", QDialogButtonBox.ButtonRole.ActionRole)
        self.none_btn.setEnabled(bool(self.icon))
        self.none_btn.setAutoDefault(False)  # Enter does not take the icon away
        self.none_btn.clicked.connect(lambda: self._finish(""))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._style()
        self._set_color(self.color)

    def _style(self):
        t = theme.current()
        swatches = "".join(
            f"QToolButton#swatch[role='{r}'] {{ background: {getattr(t, r or 'on_deep')}; }}" for r in collections.COLORS)
        self.board.setStyleSheet(f"""
            QFrame#iconboard {{ background: {t.deep_mid}; border-radius: 12px; }}
            QToolButton#symbol {{ background: transparent; border: none; border-radius: 9px; }}
            QToolButton#symbol:hover {{ background: {theme.rgba('on_deep', 0.12)}; }}
            QToolButton#symbol:checked {{ background: {theme.rgba('foam', 0.28)}; }}
            QToolButton#swatch {{ border: 2px solid transparent; border-radius: 13px; }}
            QToolButton#swatch:checked {{ border: 2px solid {t.on_deep}; }}
            {swatches}""")
        for role, b in self.swatches.items():
            b.setProperty("role", role)
            b.style().unpolish(b)
            b.style().polish(b)

    def _set_color(self, role: str):
        self.color = role
        for name, b in self.buttons.items():
            b.setIcon(icon(name, role or "on_deep"))

    def _finish(self, symbol: str):
        self.icon = collections.clean_icon(f"{symbol}:{self.color}" if symbol and self.color else symbol)
        self.accept()

    @classmethod
    def ask(cls, what: str, current: str = "", parent=None) -> str | None:
        """The icon chosen ("" for none), or None when cancelled."""
        dlg = cls(what, current, parent)
        return dlg.icon if dlg.exec() else None


class CollectionDialog(FittedDialog):
    """Several files are coming in: file them in a collection, or import them into the day-to-day
    list. `name` is the answer: a collection's name, or "" for the list."""

    def __init__(self, n: int, names: list[str], suggestion: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import")
        self.setFixedWidth(460)
        self.name = ""
        lay = QVBoxLayout(self)
        lay.addWidget(_heading(f"Import {n} files"))
        lay.addWidget(_dim("A collection keeps a batch together and out of your day-to-day list: it shows in the "
                           "sidebar and opens when you click it. Search finds its recordings like any other."))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.addItems(names)
        self.combo.setCurrentText(suggestion)
        self.combo.lineEdit().setPlaceholderText("Name a new collection, or choose one")
        self.combo.setAccessibleName("Collection")
        lay.addWidget(self.combo)
        lay.addSpacing(8)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.plain_btn = bb.addButton("Just import", QDialogButtonBox.ButtonRole.ActionRole)
        self.plain_btn.clicked.connect(lambda: self._finish(""))
        self.file_btn = bb.addButton("Import into collection", QDialogButtonBox.ButtonRole.AcceptRole)
        self.file_btn.setIcon(icon("folder", "on_accent"))
        theme.set_role(self.file_btn, primary=True)
        self.file_btn.setDefault(True)
        bb.accepted.connect(lambda: self._finish(collections.clean(self.combo.currentText())))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.combo.editTextChanged.connect(self._update)
        self._update()
        self.combo.setFocus()

    def _update(self, *_a):
        self.file_btn.setEnabled(bool(collections.clean(self.combo.currentText())))

    def _finish(self, name: str):
        self.name = name
        self.accept()

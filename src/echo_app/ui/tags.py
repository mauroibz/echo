"""Tags in the window: the chip bar that filters the list, and the editor under the title."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCompleter, QLayout, QLineEdit, QMenu, QPlainTextEdit, QSizePolicy, QToolButton,
                               QWidget, QWidgetItem)

from ..library import fold_tag, tag_category
from . import theme

MAX_CHIPS = 12  # chips shown in the bar; the rest are in a menu


class FlowLayout(QLayout):
    """Lays widgets out in rows, wrapping like words (Qt's flow layout example)."""

    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _place(self, rect: QRect, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            line = max(line, hint.height())
        return y + line - rect.y()

    def clear(self):
        while self._items:
            w = self._items.pop().widget()
            if w is not None:
                w.deleteLater()


def _chip(text: str, name: str, checkable: bool = False) -> QToolButton:
    b = QToolButton()
    b.setObjectName(name)
    b.setText(text)
    b.setCheckable(checkable)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(theme.display_font(0.82, QFont.Weight.Bold))
    return b


class TagBar(QWidget):
    """The most used tags above the list; clicking one adds or removes #tag in the search box.

    Tags of a category (`client:Acme`) share one chip whose menu holds the category's values and
    "Any client" (`#client:`); plain tags are chips of their own.
    """

    toggled = Signal(str, bool)  # tag, now active

    def __init__(self, parent=None):
        super().__init__(parent)
        self.flow = FlowLayout(self, spacing=5)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._shown: tuple = ()

    def set_tags(self, counts: list[tuple[str, int]], active: set[str], totals: dict[str, int] | None = None):
        """counts: (tag, recordings) most used first; active: folded tags in the search; totals:
        recordings with any value of each (folded) category."""
        key = (tuple(counts), tuple(sorted(active)), tuple(sorted((totals or {}).items())))
        if key == self._shown:
            return
        self._shown = key
        self.flow.clear()
        # (folded category, its spelling, recordings, [(tag, n)]) in order of use, and plain tags.
        cats: dict[str, tuple[str, list[tuple[str, int]]]] = {}
        items: list[tuple[int, object]] = []
        for tag, n in counts:
            c = tag_category(tag)
            if c is None:
                items.append((n, (tag, n)))
            else:
                cats.setdefault(fold_tag(c[0]), (c[0], []))[1].append((tag, n))
        for folded, (name, values) in cats.items():
            total = (totals or {}).get(folded) or sum(n for _t, n in values)
            items.append((total, (folded, name, total, values)))
        items.sort(key=lambda x: -x[0])  # stable: equal counts keep the order of use
        shown = [it for _n, it in items]
        for it in shown[:MAX_CHIPS]:
            self.flow.addWidget(self._category_chip(it, active) if len(it) == 4 else self._tag_chip(it, active))
        if len(shown) > MAX_CHIPS:
            more = _chip(f"more ({len(shown) - MAX_CHIPS})…", "tagchip")
            more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            more.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
            menu = QMenu(more)
            for it in shown[MAX_CHIPS:]:
                if len(it) == 4:
                    self._fill_category(menu.addMenu(f"{it[1]}  ({it[2]})"), it, active)
                else:
                    self._add_action(menu, f"#{it[0]}  ({it[1]})", it[0], active)
            more.setMenu(menu)
            self.flow.addWidget(more)
        self.setVisible(bool(counts))
        self.updateGeometry()

    def _tag_chip(self, item, active) -> QToolButton:
        tag, n = item
        b = _chip(f"#{tag}  {n}", "tagchip", checkable=True)
        b.setChecked(fold_tag(tag) in active)
        b.setToolTip(f"Show only recordings tagged “{tag}”")
        b.toggled.connect(lambda on, t=tag: self.toggled.emit(t, on))
        return b

    def _category_chip(self, item, active) -> QToolButton:
        folded, name, total, values = item
        b = _chip(f"{name} ▾  {total}", "tagchip", checkable=True)
        b.setChecked(any(a == folded + ":" or a.startswith(folded + ":") for a in active))
        b.setToolTip(f"Show recordings by {name}")
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        menu = QMenu(b)
        self._fill_category(menu, item, active)
        b.setMenu(menu)
        return b

    def _fill_category(self, menu: QMenu, item, active):
        folded, name, total, values = item
        self._add_action(menu, f"Any {name}  ({total})", f"{name}:", active)
        menu.addSeparator()
        for tag, n in values:
            self._add_action(menu, f"{tag_category(tag)[1]}  ({n})", tag, active)

    def _add_action(self, menu: QMenu, text: str, tag: str, active):
        a = menu.addAction(text)
        a.setCheckable(True)
        a.setChecked(fold_tag(tag) in active)
        a.toggled.connect(lambda on, t=tag: self.toggled.emit(t, on))


class TagEditor(QWidget):
    """A recording's tags as removable chips, and a field to add one (with completion)."""

    changed = Signal(list)  # the new list of tags

    def __init__(self, parent=None):
        super().__init__(parent)
        self.flow = FlowLayout(self, spacing=5)
        self.tags: list[str] = []
        self.entry = QLineEdit()
        self.entry.setObjectName("tagentry")
        self.entry.setPlaceholderText("+ tag")
        self.entry.setAccessibleName("Add a tag")
        self.entry.setFixedWidth(110)
        self.entry.returnPressed.connect(self._add)
        self._completer = QCompleter([], self.entry)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.entry.setCompleter(self._completer)
        self._chips: list[QToolButton] = []
        self.flow.addWidget(self.entry)

    def set_known(self, tags: list[str]):
        """Tags used anywhere in the library, offered as the user types."""
        self._completer.model().setStringList(tags)

    def set_tags(self, tags: list[str]):
        if list(tags) == self.tags and self._chips:
            return
        self.tags = list(tags)
        for c in self._chips:
            self.flow.removeWidget(c)
            c.deleteLater()
        self._chips = []
        self.flow.removeWidget(self.entry)
        for t in self.tags:
            c = tag_category(t)
            b = _chip(f"{c[0]} › {c[1]}  ×" if c else f"#{t}  ×", "tageditchip")
            b.setToolTip(f"Remove “{t}”")
            b.clicked.connect(lambda _c=False, tag=t: self._remove(tag))
            self.flow.addWidget(b)
            self._chips.append(b)
        self.flow.addWidget(self.entry)
        self.updateGeometry()

    def _add(self):
        text = self.entry.text().strip().lstrip("#")
        self.entry.clear()
        if text and fold_tag(text) not in {fold_tag(t) for t in self.tags}:
            self.changed.emit(self.tags + [text])

    def _remove(self, tag: str):
        self.changed.emit([t for t in self.tags if t != tag])

    def sizeHint(self):
        return QSize(300, self.flow.heightForWidth(max(self.width(), 300)))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self.flow.heightForWidth(w)


class NotesEdit(QPlainTextEdit):
    """Notes for a recording: one line at rest, three while editing; saved when focus leaves."""

    edited = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notes")
        self.setPlaceholderText("Notes")
        self.setAccessibleName("Notes")
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._lines(1)

    def _lines(self, n: int):
        h = self.fontMetrics().lineSpacing() * n + 2 * int(self.document().documentMargin()) + 6
        self.setFixedHeight(h)

    def focusInEvent(self, e):
        self._lines(3)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._lines(1)
        super().focusOutEvent(e)
        self.edited.emit(self.toPlainText().strip())

    def set_text(self, text: str):
        if not self.hasFocus() and self.toPlainText() != text:
            self.setPlainText(text)

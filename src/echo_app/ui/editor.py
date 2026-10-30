"""The transcript editor: the text widget with its margin of times, markers and speaker names,
and the centered state view shown when there is no text."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QMouseEvent, QPainter, QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from .. import export
from . import theme
from .common import icon
from .transcript_text import BASE_MARGIN, HEAD_ROOM


class TimestampMargin(QWidget):
    """The editor's left margin: passage start times, and a dot where a marker falls."""

    DOT = 14  # width of the marker column
    LABEL_MAX = 120  # widest speaker name before it is elided

    def __init__(self, editor: "Editor"):
        super().__init__(editor)
        self.editor = editor
        self.stamps: list[tuple[int, float]] = []  # character position, seconds
        self.marks: list[tuple[int, dict]] = []  # character position of the passage, marker
        self.labels: list[tuple[int, str, str, int]] = []  # position, speaker name, color role, number
        self.setFont(theme.display_font(0.82, QFont.Weight.DemiBold, tabular=True))
        self.setMouseTracking(True)

    def _label_width(self) -> int:
        if not self.labels:
            return 0
        fm = self.fontMetrics()
        return min(self.LABEL_MAX, max(fm.horizontalAdvance(t) for _p, t, _c, _n in self.labels)) + 12

    def width_needed(self) -> int:
        w = (self.DOT if self.marks else 0) + self._label_width()
        if self.stamps:
            longest = max((export.stamp(t) for _p, t in self.stamps), key=len, default="0:00")
            w += self.fontMetrics().horizontalAdvance(longest) + 14
        return w + 4

    def _rect_of(self, pos: int):
        doc = self.editor.document()
        cur = QTextCursor(doc)
        cur.setPosition(min(pos, doc.characterCount() - 1))
        return self.editor.cursorRect(cur)

    def _dots(self):
        """(rect, marker) for each marker dot on screen."""
        out = []
        for pos, m in self.marks:
            r = self._rect_of(pos)
            if -r.height() < r.top() < self.height():
                out.append((QRect(2, r.top() + (r.height() - 9) // 2, 9, 9), m))
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme.current()
        p.setPen(QColor(t.muted))
        line = self.editor.fontMetrics().height()
        last_y = None
        dot = self.DOT if self.marks else 0
        label_w = self._label_width()
        left = dot + label_w
        fm = self.fontMetrics()
        for pos, text, role, _n in self.labels:
            r = self._rect_of(pos)
            if r.bottom() < 0 or r.top() > self.height():
                continue
            p.setPen(theme.color(role))
            p.drawText(QRect(dot, r.top(), label_w - 8, r.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(text, Qt.TextElideMode.ElideRight, label_w - 8))
        p.setPen(QColor(t.muted))
        for pos, sec in self.stamps:
            r = self._rect_of(pos)
            if r.bottom() < 0:
                continue
            if r.top() > self.height():
                break
            if last_y is not None and r.top() < last_y + line * 0.8:
                continue  # two passages start on one line: the first one's time is enough
            p.drawText(QRect(left, r.top(), self.width() - left - 10, r.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, export.stamp(sec))
            last_y = r.top()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.coral_deep))
        for rect, _m in self._dots():
            p.drawEllipse(rect)
        p.end()

    def _dot_at(self, pt):
        return next((m for rect, m in self._dots() if rect.adjusted(-3, -3, 3, 3).contains(pt)), None)

    def _label_at(self, pt):
        dot = self.DOT if self.marks else 0
        if not self.labels or not dot <= pt.x() < dot + self._label_width():
            return None
        for pos, _text, _role, n in self.labels:
            r = self._rect_of(pos)
            if r.top() <= pt.y() <= r.bottom():
                return n
        return None

    def mouseMoveEvent(self, e):
        m = self._dot_at(e.position().toPoint())
        speaker = self._label_at(e.position().toPoint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if m or speaker else Qt.CursorShape.ArrowCursor)
        if speaker is not None:
            from PySide6.QtWidgets import QToolTip

            QToolTip.showText(e.globalPosition().toPoint(), "Click to name this speaker", self)
        if m:
            from PySide6.QtWidgets import QToolTip

            QToolTip.showText(e.globalPosition().toPoint(),
                              f"Marker at {export.stamp(m['at'])}" + (f": {m['note']}" if m.get("note") else "")
                              + "\nClick to play from here", self)

    def mousePressEvent(self, e):
        m = self._dot_at(e.position().toPoint())
        if m:
            self.editor.marker_clicked.emit(float(m["at"]))
            return
        n = self._label_at(e.position().toPoint())
        if n is not None:
            self.editor.speaker_clicked.emit(n, e.globalPosition().toPoint())


class Editor(QPlainTextEdit):
    ctrl_clicked = Signal(int)  # character position
    clicked = Signal(int)  # character position of a plain click that selected nothing
    heading_clicked = Signal(int)  # a linked set's part number (from 0)
    marker_clicked = Signal(float)  # seconds
    speaker_clicked = Signal(int, object)  # speaker number, global position
    MAX_TEXT_WIDTH_CHARS = 90

    def __init__(self, parent=None):
        super().__init__(parent)
        self.menu_hook = None  # callable(menu, position) adding actions for the clicked spot
        self.tooltip_hook = None  # callable(position) -> tooltip text for that spot, or None
        self.key_hook = None  # called on every typing key, before the edit
        # A linked set: edit_guard(lo, hi) says whether the text between two positions may change
        # (False across or inside a part's heading); heading_at(pos) is the part whose heading is there.
        self.edit_guard = None
        self.heading_at = None
        self.margin = TimestampMargin(self)
        self.margin.hide()
        self.updateRequest.connect(lambda _r, _dy: self.margin.update())
        # Speaker names drawn over their turns: (position, name, color role, number), and where
        # each was drawn, for clicks.
        self.heads: list[tuple[int, str, str, int]] = []
        self.labels: list[tuple[int, str, str, int]] = []
        self._head_rects: list[tuple[QRect, int]] = []
        self.head_font = theme.display_font(0.8, QFont.Weight.ExtraBold)

    def set_stamps(self, stamps: list[tuple[int, float]] | None, marks: list[tuple[int, dict]] = (),
                   labels=()):
        """Show passage times (character position, seconds), marker dots and speaker names;
        nothing hides the margin. A name goes over its turn when the turn starts a paragraph after a
        blank line (or the text), and in the margin otherwise, so it never covers text."""
        doc = self.document()
        self.labels = list(labels)  # every speaker name, wherever it is drawn
        heads, side = [], []
        for lab in labels:
            block = doc.findBlock(lab[0])
            prev = block.previous()
            starts = block.isValid() and lab[0] == block.position()
            if starts and (block.blockNumber() == 0 or (prev.isValid() and not prev.text().strip())):
                heads.append(lab)
            else:
                side.append(lab)
        self.heads = heads
        room = HEAD_ROOM if any(doc.findBlock(h[0]).blockNumber() == 0 for h in heads) else BASE_MARGIN
        if doc.documentMargin() != room:
            doc.setDocumentMargin(room)
        self.viewport().update()
        self.margin.stamps = stamps or []
        self.margin.marks = list(marks)
        self.margin.labels = side
        if not self.margin.stamps and not self.margin.marks and not self.margin.labels:
            self.margin.hide()
            self.setViewportMargins(0, 0, 0, 0)
            return
        self.setViewportMargins(self.margin.width_needed(), 0, 0, 0)
        self._place_margin()
        self.margin.show()
        self.margin.update()

    def _place_margin(self):
        cr = self.contentsRect()
        self.margin.setGeometry(QRect(cr.left(), cr.top(), self.viewportMargins().left(), cr.height()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_margin()

    def _edit_range(self, e) -> tuple[int, int] | None:
        """The text a key would change, or None for keys that change nothing (moving, copying)."""
        cur = self.textCursor()
        a, b = cur.selectionStart(), cur.selectionEnd()
        K, SK = Qt.Key, QKeySequence.StandardKey
        word_back = e.matches(SK.DeleteStartOfWord)
        word_fwd = e.matches(SK.DeleteEndOfWord) or e.matches(SK.DeleteEndOfLine)
        if e.matches(SK.Undo) or e.matches(SK.Redo) or e.matches(SK.Copy) or e.matches(SK.SelectAll):
            return None
        if e.matches(SK.Cut) or e.matches(SK.Paste):
            return a, b
        if e.key() in (K.Key_Backspace, K.Key_Delete) or word_back or word_fwd:
            if a != b:
                return a, b
            c = QTextCursor(cur)
            if word_back:
                c.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
            elif word_fwd:
                c.movePosition(QTextCursor.MoveOperation.EndOfWord if e.matches(SK.DeleteEndOfWord)
                               else QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                if c.position() == a:
                    c.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            elif e.key() == K.Key_Backspace:
                c.movePosition(QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.KeepAnchor)
            else:
                c.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            return min(c.position(), c.anchor()), max(c.position(), c.anchor())
        if e.text() and not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            return a, b  # typing (Enter and Tab too) replaces the selection
        return None

    def keyPressEvent(self, e):
        if self.edit_guard is not None:
            rng = self._edit_range(e)
            if rng is not None and not self.edit_guard(*rng):
                e.accept()  # the part's heading, or another part: nothing changes
                return
        if self.key_hook and e.text() and not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                                | Qt.KeyboardModifier.AltModifier)):
            self.key_hook()
        elif self.key_hook and e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.key_hook()
        super().keyPressEvent(e)

    def inputMethodEvent(self, e):
        # Accented letters often arrive this way (IBus), bypassing keyPressEvent.
        if self.edit_guard is not None and (e.commitString() or e.preeditString() or e.replacementLength()):
            cur = self.textCursor()
            lo, hi = cur.selectionStart(), cur.selectionEnd()
            if e.replacementLength():
                lo, hi = min(lo, cur.position() + e.replacementStart()), \
                    max(hi, cur.position() + e.replacementStart() + e.replacementLength())
            if not self.edit_guard(lo, hi):
                e.accept()
                return
        super().inputMethodEvent(e)

    def insertFromMimeData(self, source):
        if self.edit_guard is not None:
            cur = self.textCursor()
            if not self.edit_guard(cur.selectionStart(), cur.selectionEnd()):
                return
        super().insertFromMimeData(source)

    def paintEvent(self, e):
        super().paintEvent(e)
        self._head_rects = []
        if not self.heads:
            return
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(self.head_font)
        fm = p.fontMetrics()
        doc = self.document()
        h = self.viewport().height()
        for pos, name, role, n in self.heads:
            block = doc.findBlock(pos)
            if not block.isValid():
                continue
            here = self.cursorRect(QTextCursor(block))
            if block.blockNumber() == 0:
                bottom = here.top() - 2
            else:
                prev = block.previous()
                if prev.text().strip():
                    continue  # typed into the blank line since: the name waits for the next layout
                bottom = here.top() - 2
            top = bottom - fm.height()
            if bottom < 0 or top > h:
                continue
            x = here.left()
            dot = 8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(role))
            p.drawEllipse(x, top + (fm.height() - dot) // 2, dot, dot)
            p.setPen(theme.color(role))
            w = fm.horizontalAdvance(name)
            p.drawText(QRect(x + dot + 7, top, w + 2, fm.height()), Qt.AlignmentFlag.AlignVCenter, name)
            self._head_rects.append((QRect(x - 2, top - 2, dot + 7 + w + 6, fm.height() + 4), n))
        p.end()

    def _head_at(self, pt) -> int | None:
        return next((n for r, n in self._head_rects if r.contains(pt)), None)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton and not e.modifiers():
            n = self._head_at(e.position().toPoint())
            if n is not None:
                self.speaker_clicked.emit(n, e.globalPosition().toPoint())
                return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and e.button() == Qt.MouseButton.LeftButton:
            self.ctrl_clicked.emit(self.cursorForPosition(e.position().toPoint()).position())
            return
        if self.heading_at is not None and e.button() == Qt.MouseButton.LeftButton:
            k = self.heading_at(self.cursorForPosition(e.position().toPoint()).position())
            if k is not None:
                self.heading_clicked.emit(k)
                return
        self._plain_press = e.button() == Qt.MouseButton.LeftButton and not e.modifiers()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        super().mouseReleaseEvent(e)
        # On release, so a drag that selects words or a double-click on one does not move playback.
        if getattr(self, "_plain_press", False) and e.button() == Qt.MouseButton.LeftButton:
            self._plain_press = False
            if not self.textCursor().hasSelection():
                self.clicked.emit(self.textCursor().position())

    def mouseMoveEvent(self, e: QMouseEvent):
        if not e.buttons() and self._head_rects:
            on = self._head_at(e.position().toPoint()) is not None
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.IBeamCursor)
            if on:
                from PySide6.QtWidgets import QToolTip

                QToolTip.showText(e.globalPosition().toPoint(), "Name, merge or open this speaker", self)
                super().mouseMoveEvent(e)
                return
        if self.heading_at is not None and not e.buttons():
            k = self.heading_at(self.cursorForPosition(e.position().toPoint()).position())
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if k is not None
                                      else Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(e)

    def event(self, e):
        if e.type() == e.Type.ToolTip and self.tooltip_hook:
            from PySide6.QtWidgets import QToolTip

            pos = self.viewport().mapFromGlobal(e.globalPos())
            tip = self.tooltip_hook(self.cursorForPosition(pos).position())
            if tip:
                QToolTip.showText(e.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def contextMenuEvent(self, e):
        menu = self.createStandardContextMenu(e.pos())
        if self.edit_guard is not None:
            cur = self.textCursor()
            if not self.edit_guard(cur.selectionStart(), cur.selectionEnd()):
                for a in menu.actions():
                    if a.objectName() in ("edit-cut", "edit-paste", "edit-delete"):
                        a.setEnabled(False)
        if self.menu_hook:
            self.menu_hook(menu, self.cursorForPosition(e.pos()).position())
        menu.exec(e.globalPos())
        menu.deleteLater()


class StateView(QWidget):
    """Centered message with optional progress bar and buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.glyph = QLabel()
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.glyph)
        self.headline = QLabel()
        self.headline.setFont(theme.display_font(1.35, QFont.Weight.ExtraBold))
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.detail = QLabel()
        theme.set_role(self.detail, dim=True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setOpenExternalLinks(True)
        lay.addWidget(self.detail)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(360)
        self.progress.setTextVisible(False)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.progress)
        row.addStretch(1)
        lay.addLayout(row)
        self.buttons = QHBoxLayout()
        self.buttons.addStretch(1)
        self._btn_end = QWidget()
        lay.addLayout(self.buttons)
        lay.addStretch(2)
        self._btns: list[QPushButton] = []

    def show_state(self, headline: str, detail: str = "", progress: float | None = None,
                   busy: bool = False, actions=(), glyph: str = "transcribe"):
        self.glyph.setPixmap(icon(glyph, "accent").pixmap(QSize(44, 44), self.devicePixelRatioF()))
        self.headline.setText(headline)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        if progress is None and not busy:
            self.progress.hide()
        else:
            self.progress.show()
            if progress is None:
                self.progress.setRange(0, 0)
            else:
                self.progress.setRange(0, 1000)
                self.progress.setValue(int(progress * 1000))
        for b in self._btns:
            self.buttons.removeWidget(b)
            b.deleteLater()
        self._btns = []
        # Remove the trailing stretch, add buttons, re-add stretch.
        while self.buttons.count():
            self.buttons.takeAt(0)
        self.buttons.addStretch(1)
        for label, ic, fn, default in actions:
            b = QPushButton(icon(ic), label)
            b.clicked.connect(fn)
            if default:
                b.setDefault(True)
                theme.set_role(b, primary=True)
            self.buttons.addWidget(b)
            self._btns.append(b)
        self.buttons.addStretch(1)

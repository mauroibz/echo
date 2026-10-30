"""The input's controls: the level meter, the input list and the panel that opens under Record."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QComboBox, QFrame, QSizePolicy, QStyledItemDelegate, QVBoxLayout, QWidget

from . import theme

FLOOR_DB = -60.0  # the meter's bottom


class LevelMeter(QWidget):
    """Horizontal peak meter with a decaying peak-hold mark and a clip lamp."""

    def __init__(self, parent=None, on_deep: bool = True):
        super().__init__(parent)
        self.on_deep = on_deep  # drawn on the sidebar's deep gradient, or on a light surface
        self.setMinimumHeight(14)
        self.setMaximumHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._level = FLOOR_DB
        self._hold = FLOOR_DB
        self._hold_t = 0.0
        self._clip_until = 0.0
        self._note = ""
        self.setToolTip("Input level. Keep the loudest parts out of the red.")
        self.setAccessibleName("Input level")

    def set_level(self, db: float, clipped: bool = False) -> None:
        now = time.monotonic()
        # Fast attack, smooth release.
        self._level = db if db > self._level else max(db, self._level - 1.5)
        if db >= self._hold or now - self._hold_t > 1.2:
            self._hold, self._hold_t = db, now
        if clipped:
            self._clip_until = now + 2.0
        self.update()

    def set_note(self, text: str, tip: str = "") -> None:
        """A few words drawn on the bar while it is empty (the input is silent); `tip` explains them."""
        if text != self._note:
            self._note = text
            self.setToolTip(tip or "Input level. Keep the loudest parts out of the red.")
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(200, 14)

    @staticmethod
    def _frac(db: float) -> float:
        return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme.current()
        lamp = 8
        h = self.height()
        r = QRectF(0, (h - 6) / 2, self.width() - lamp - 8, 6)
        p.setPen(Qt.PenStyle.NoPen)
        ground = "on_deep" if self.on_deep else "muted"
        p.setBrush(theme.color(ground, 0.14 if self.on_deep else 0.18))
        p.drawRoundedRect(r, 3, 3)
        w = r.width() * self._frac(self._level)
        if w > 0:
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0.0, QColor(t.accent))
            g.setColorAt(0.70, QColor(t.foam))
            g.setColorAt(0.86, QColor(t.amber))
            g.setColorAt(1.0, QColor(t.coral_deep))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(r.left(), r.top(), max(w, 6), r.height()), 3, 3)
        if self._hold > FLOOR_DB + 1:
            hx = r.left() + r.width() * self._frac(self._hold)
            p.setBrush(theme.color("on_deep" if self.on_deep else "ink", 0.9))
            p.drawRoundedRect(QRectF(hx - 1, r.top() - 2, 2, r.height() + 4), 1, 1)
        if self._note:
            f = p.font()
            f.setPixelSize(max(9, h - 3))
            p.setFont(f)
            p.setPen(QColor(t.amber))
            p.drawText(r.adjusted(4, -6, 0, 6), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       self._note)
            p.setPen(Qt.PenStyle.NoPen)
        clipping = time.monotonic() < self._clip_until
        p.setBrush(QColor(t.coral_deep) if clipping else theme.color(ground, 0.18))
        p.drawEllipse(QRectF(self.width() - lamp, (h - lamp) / 2, lamp, lamp))


class SourceCombo(QComboBox):
    aboutToShow = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # The default combo delegate paints items in the combo's own (light, on-sidebar) text color;
        # a styled delegate follows the popup's stylesheet rules instead.
        self.setItemDelegate(QStyledItemDelegate(self))

    def showPopup(self):
        self.aboutToShow.emit()
        super().showPopup()


class InputPanel(QFrame):
    """A popup under the input's name: the input list, listen, level, gain and computer audio."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("sidebar")  # styled as the sidebar it opens from
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 16)
        self.body.setSpacing(10)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(theme.color("on_deep", 0.18))
        p.setBrush(theme.deep_gradient(r))
        p.drawRoundedRect(r, 14, 14)
        p.end()

"""Studio's look on top of Lagoon: the deep hero band ending in waves, avatars, and the timeline.

Everything paints from `theme.current()` at paint time, and the few style sheets are rebuilt on
a palette change, so light and dark switch live as in the rest of Echo.
"""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from echo_app.ui import theme

AVATAR_ROLES = ("accent_deep", "orange", "violet", "coral_deep", "accent")  # each readable under white in both themes


def initials(name: str) -> str:
    """"Carla Méndez" → CM; an address by its name part: ana.suarez@acme.example → AS."""
    name = name.split("@")[0] if "@" in name else name
    parts = [p for p in name.replace(".", " ").replace("_", " ").split() if p[:1].isalnum()]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def avatar_color(name: str) -> QColor:
    h = int(hashlib.sha1(name.strip().lower().encode()).hexdigest()[:4], 16)
    return theme.color(AVATAR_ROLES[h % len(AVATAR_ROLES)])


class Avatar(QWidget):
    """A person's initials in a circle of their color; `ring` draws an outline in the hero's color
    so stacked avatars read apart."""

    def __init__(self, name: str, size: int = 34, ring: str | None = None, parent=None):
        super().__init__(parent)
        self.name, self.size_, self.ring = name, size, ring
        self.setFixedSize(size, size)
        self.setToolTip(name)
        self.setAccessibleName(name)

    def sizeHint(self) -> QSize:
        return QSize(self.size_, self.size_)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.ring:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(self.ring))
            p.drawEllipse(r)
            r = r.adjusted(2.5, 2.5, -2.5, -2.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(avatar_color(self.name))
        p.drawEllipse(r)
        f = theme.display_font(1.0, QFont.Weight.ExtraBold)
        f.setPixelSize(max(9, int(r.height() * 0.38)))
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, initials(self.name))
        p.end()


class AvatarStack(QWidget):
    """Overlapping avatars, up to `limit`."""

    def __init__(self, names: list[str], size: int = 30, ring: str = "surface", limit: int = 5):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(-size // 4)
        for n in names[:limit]:
            lay.addWidget(Avatar(n, size, ring))
        lay.addStretch(1)


class Hero(QWidget):
    """The deep band at the top of Studio's screens: Lagoon's gradient on a slant, slow swells along
    its bottom, and the canvas cutting in as a wave so the page flows out of it. `live` turns the
    front swell coral (a recording)."""

    WAVE_H = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self.live = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setObjectName("hero")
        self._style()

    def _style(self):
        t = self._tokens = theme.current()
        self.setStyleSheet(f"""
            QWidget#hero QLabel {{ color: {t.on_deep}; background: transparent; }}
            QWidget#hero QLabel[dim="true"] {{ color: {t.on_deep_muted}; }}
            QWidget#hero QLabel[eyebrow="true"] {{ color: {t.coral if self.live else t.foam}; font-weight: 800;
                letter-spacing: 1.6px; }}
            QWidget#hero QPushButton {{ background: {t.foam}; color: {t.deep_top}; border: none; border-radius: 14px;
                padding: 10px 18px; font-weight: 800; }}
            QWidget#hero QPushButton:hover {{ background: {t.on_deep}; }}
            QWidget#hero QPushButton[quiet="true"] {{ background: {theme.rgba('on_deep', 0.10)}; color: {t.on_deep};
                border: 1px solid {theme.rgba('on_deep', 0.28)}; border-radius: 999px; padding: 5px 12px;
                font-weight: 700; }}
            QWidget#hero QPushButton[quiet="true"]:hover {{ background: {theme.rgba('on_deep', 0.18)}; }}
            QWidget#hero QPushButton[stop="true"] {{ background: {t.coral_deep}; color: #ffffff; }}
            QWidget#hero QPlainTextEdit {{ background: {theme.rgba('on_deep', 0.08)}; color: {t.on_deep};
                border: 1px solid {theme.rgba('on_deep', 0.22)}; border-radius: 12px; padding: 8px; }}
        """)

    def set_live(self, on: bool):
        if on != self.live:
            self.live = on
            self._style()
            self.update()

    def changeEvent(self, e):
        # Restyled when the theme changes; setting the style sheet sends another palette change,
        # so only a new set of tokens restyles.
        if e.type() == QEvent.Type.PaletteChange and self._tokens is not theme.current():
            self._style()
        super().changeEvent(e)

    def paintEvent(self, _):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, QColor(t.deep_top))
        g.setColorAt(0.6, QColor(t.deep_mid))
        g.setColorAt(1.0, QColor(t.deep_bottom))
        p.fillRect(r, g)
        band = QRectF(r.left(), r.bottom() - self.WAVE_H * 2.2, r.width(), self.WAVE_H * 2.2)
        theme.paint_waves(p, band.adjusted(0, 0, 0, -self.WAVE_H * 0.55), 0.8, 0.45 if self.live else 0.15)
        # The canvas comes in as one long swell.
        w, bottom = r.width(), r.bottom() + 1
        path = QPainterPath(QPointF(r.left(), bottom))
        path.lineTo(r.left(), bottom - self.WAVE_H * 0.42)
        path.cubicTo(QPointF(w * 0.22, bottom - self.WAVE_H * 0.95), QPointF(w * 0.48, bottom - self.WAVE_H * 0.05),
                     QPointF(w * 0.7, bottom - self.WAVE_H * 0.45))
        path.cubicTo(QPointF(w * 0.84, bottom - self.WAVE_H * 0.7), QPointF(w * 0.94, bottom - self.WAVE_H * 0.55),
                     QPointF(w, bottom - self.WAVE_H * 0.5))
        path.lineTo(w, bottom)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.canvas))
        p.drawPath(path)
        p.end()


def label(text: str = "", scale: float = 1.0, weight: QFont.Weight = QFont.Weight.Normal, display: bool = True,
          dim: bool = False, eyebrow: bool = False, wrap: bool = False, tabular: bool = False) -> QLabel:
    lbl = QLabel(text)
    if display:
        lbl.setFont(theme.display_font(scale, weight, tabular=tabular))
    else:
        f = theme.reading_font(scale)
        f.setWeight(weight)
        lbl.setFont(f)
    if dim:
        theme.set_role(lbl, dim=True)
    if eyebrow:
        theme.set_role(lbl, eyebrow=True)
    lbl.setWordWrap(wrap)
    return lbl


def minutes_long(seconds: float) -> str:
    """"38 min", "1 h 05": how long a meeting was, as people say it."""
    m = max(1, round((seconds or 0) / 60))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


class TimelineDot(QWidget):
    """The rail of the minutes timeline: a dot (filled for today) and the line down to the next."""

    def __init__(self, filled: bool, last: bool):
        super().__init__()
        self.filled, self.last = filled, last
        self.setFixedWidth(26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2
        if not self.last:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("accent", 0.28))
            p.drawRect(QRectF(cx - 1, 30, 2, self.height() - 30))
        p.setPen(theme.color("accent"))
        p.setBrush(theme.color("accent") if self.filled else theme.color("canvas"))
        p.drawEllipse(QPointF(cx, 26), 6, 6)
        p.end()

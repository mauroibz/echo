"""Shared UI helpers: icons, background tasks, formatting, persisted layout."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QObject, QRectF, QRunnable, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .. import paths
from . import theme
from ..fsutil import atomic_write_json

log = logging.getLogger(__name__)

# Icon names used in the UI, mapped to the bundled Lucide set (see theme.TintedIcon).
_ICONS = {
    "pause": "pause", "stop": "square", "play": "play", "listen": "headphones", "copy": "copy",
    "export": "upload", "import": "download", "delete": "trash-2", "rename": "pencil", "transcribe": "audio-lines",
    "revert": "undo-2", "cancel": "x", "close": "x", "folder": "folder-open", "find": "search",
    "settings": "settings", "crop": "crop", "clear": "eraser", "help": "circle-help", "warning": "triangle-alert",
    "error": "circle-alert", "ok": "circle-check", "download": "download", "more": "ellipsis", "mic": "mic",
    "set": "layers", "link": "link", "unlink": "unlink", "expand": "chevron-right", "collapse": "chevron-down",
}


def icon(name: str, role: str = "ink") -> QIcon:
    """A bundled icon tinted with a theme color role; "record" is the coral dot."""
    if name == "record":
        return dot_icon(theme.color("coral_deep"))
    return theme.tinted(_ICONS.get(name, name), role)


def dot_icon(color: QColor, size: int = 32, ring: bool = False) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    if ring:
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawEllipse(1, 1, size - 2, size - 2)
    p.setBrush(color)
    m = size // 5
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    p.end()
    return QIcon(pm)


def app_icon() -> QIcon:
    ic = QIcon.fromTheme("echo-app")
    if ic.isNull():
        svg = paths.repo_root() / "data" / "echo-app.svg"
        ic = QIcon(str(svg)) if svg.exists() else dot_icon(RECORD_RED)
    return ic


RECORD_RED = QColor(theme.LAGOON_LIGHT.coral_deep)


# ---- background tasks -------------------------------------------------------------------------

class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(object)


class Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args, with_progress: bool = False):
        super().__init__()
        self.fn, self.args, self.with_progress = fn, args, with_progress
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            if self.with_progress:
                result = self.fn(*self.args, progress=self.signals.progress.emit)
            else:
                result = self.fn(*self.args)
        except Exception as e:  # noqa: BLE001 - reported to the UI
            log.error("background task failed: %s", traceback.format_exc())
            self._emit(self.signals.failed, str(e) or e.__class__.__name__)
            return
        self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal, value) -> None:
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # the window that asked is gone (closing, or a test's window torn down)


_keep: set[Task] = set()


def run_task(fn: Callable[..., Any], *args, on_done: Callable[[Any], None] | None = None,
             on_error: Callable[[str], None] | None = None, on_progress: Callable[[Any], None] | None = None,
             parent: QObject | None = None) -> Task:
    task = Task(fn, *args, with_progress=on_progress is not None)
    _keep.add(task)

    def finish(*_):
        _keep.discard(task)

    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    if on_progress:
        task.signals.progress.connect(on_progress)
    task.signals.done.connect(finish)
    task.signals.failed.connect(finish)
    QThreadPool.globalInstance().start(task)
    return task


# ---- formatting -------------------------------------------------------------------------------

def fmt_duration(sec: float | None, always_hours: bool = False) -> str:
    if sec is None:
        return "--:--"
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h or always_hours else f"{m}:{s:02d}"


def fmt_eta(sec: float | None) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    if sec < 60:
        return "less than a minute left"
    m = round(sec / 60)
    return f"about {m} min left" if m < 60 else f"about {m // 60} h {m % 60:02d} min left"


def fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    now = datetime.now(dt.tzinfo)
    if dt.date() == now.date():
        return f"Today {dt:%H:%M}"
    if (now.date() - dt.date()).days == 1:
        return f"Yesterday {dt:%H:%M}"
    if dt.year == now.year:
        return f"{dt:%b %-d, %H:%M}"
    return f"{dt:%b %-d %Y}"


# ---- persisted UI state -----------------------------------------------------------------------

class UiState:
    def __init__(self):
        self.path = paths.state_dir() / "ui.json"
        try:
            self.data: dict[str, Any] = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def save(self) -> None:
        try:
            atomic_write_json(self.path, self.data, mkdir=True)
        except OSError:
            log.warning("could not save UI state")


# ---- the wordmark -----------------------------------------------------------------------------

class Wordmark(QWidget):
    """"echo" as a mark on the deep gradient: the word in a light gradient, and arcs centered on its
    last "o" spreading out to the right and fading, like an echo."""

    RINGS = ((1.32, 0.55), (1.72, 0.3), (2.12, 0.14))  # (radius in radii of the "o", opacity)
    SPAN = 100  # degrees of each arc, centered on the right

    def __init__(self, scale: float = 2.1, parent=None):
        from PySide6.QtWidgets import QSizePolicy

        super().__init__(parent)
        self.font_ = theme.display_font(scale, QFont.Weight.ExtraBold)
        self.setAccessibleName("Echo")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _paths(self):
        from PySide6.QtGui import QFontMetricsF, QPainterPath

        word, o = QPainterPath(), QPainterPath()
        word.addText(0, 0, self.font_, "echo")
        o.addText(QFontMetricsF(self.font_).horizontalAdvance("ech"), 0, self.font_, "o")
        # Glyph outlines overlap inside a letter; filled odd-even, the overlaps would show as holes.
        word.setFillRule(Qt.FillRule.WindingFill)
        return word, o.boundingRect()

    def sizeHint(self) -> QSize:
        word, ob = self._paths()
        r = word.boundingRect()
        reach = ob.center().x() + ob.width() / 2 * self.RINGS[-1][0]
        return QSize(int(reach - r.left()) + 8, int(r.height()) + 6)

    def paintEvent(self, _):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QLinearGradient, QPen

        t = theme.current()
        word, ob = self._paths()
        r = word.boundingRect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(3 - r.left(), 3 - r.top())
        c, radius = ob.center(), ob.width() / 2
        for scale, alpha in self.RINGS:
            col = QColor(t.foam)
            col.setAlphaF(alpha)
            pen = QPen(col, max(1.2, radius * 0.2))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rr = radius * scale
            p.drawArc(QRectF(c.x() - rr, c.y() - rr, 2 * rr, 2 * rr), -self.SPAN * 8, self.SPAN * 16)
        grad = QLinearGradient(QPointF(0, r.top()), QPointF(0, r.bottom()))
        grad.setColorAt(0.0, QColor("#ffffff"))
        grad.setColorAt(0.5, QColor(t.on_deep))
        grad.setColorAt(1.0, QColor(t.foam))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(word)
        p.end()

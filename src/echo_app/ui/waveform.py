"""The waveform: the whole recording drawn once, with the playhead, crop handles and markers."""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QInputDialog, QMenu, QSizePolicy, QToolTip, QWidget

from ..audio import peaks as peaks_mod
from . import motion, theme
from .common import fmt_duration, icon

log = logging.getLogger(__name__)


HANDLE_GRAB_PX = 7
BAR_STEP = 3  # waveform bar pitch in pixels (2 px bar, 1 px gap)
NUDGE_FINE = 0.1
NUDGE_COARSE = 1.0
class WaveformView(QWidget):
    seek_requested = Signal(float)
    crop_changed = Signal(object, object)  # start, end (None = unset)
    markers_edited = Signal(list)  # the user's markers after a move, removal, note or addition

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Waveform")
        self.setToolTip("Click to seek. Drag the edges to crop; hold Shift to place freely.\n"
                        "[ and ] set the crop at the playhead; Ctrl+arrows nudge it.\n"
                        "Markers: drag to move, right-click to edit or remove, Ctrl+double-click to add.")
        self.peaks: np.ndarray | None = None
        self.duration = 0.0
        self.position = 0.0
        self.crop_start: float | None = None
        self.crop_end: float | None = None
        self.gaps: list[float] = []  # capture interruptions
        self.markers: list[dict] = []  # the user's markers: {"at", "note"}
        self.placeholder = ""
        # A linked set is shown read-only: no crop handles and no marker editing (both belong to
        # one recording), with a divider and the part number where each part starts.
        self.editable = True
        self.dividers: list[float] = []
        self._drag: str | None = None  # "start" | "end" | "seek" | "marker"
        self._drag_marker = -1
        self._last_handle = "start"
        self._cache_key = None
        self._columns = None
        self._drop_at: float | None = None  # the marker dropping in, and how far (0..1)
        self._drop_p = 1.0

    def _drop(self, at: float):
        if not motion.on():
            return
        self._drop_at, self._drop_p = at, 0.0
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(420)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        anim.valueChanged.connect(self._drop_frame)
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _drop_frame(self, v):
        self._drop_p = float(v)
        self.update()

    # ---- data ----
    def set_recording(self, duration: float, crop_start, crop_end, gaps=(), markers=()):
        self.duration = max(0.0, duration or 0.0)
        self.crop_start, self.crop_end = crop_start, crop_end
        self.gaps = list(gaps)
        self.markers = [dict(m) for m in markers]
        self.position = crop_start or 0.0
        self.update()

    def set_peaks(self, peaks: np.ndarray | None):
        self.peaks = peaks
        self._columns = None
        if peaks is not None and len(peaks) and not self.duration:
            self.duration = len(peaks) / peaks_mod.BUCKETS_PER_SECOND
        self.update()

    def set_position(self, sec: float):
        if abs(sec - self.position) > 1e-3:
            self.position = sec
            self.update()

    # ---- geometry ----
    def _x(self, t: float) -> float:
        return 0.0 if self.duration <= 0 else t / self.duration * self.width()

    def _t(self, x: float) -> float:
        return 0.0 if self.width() <= 0 else max(0.0, min(self.duration, x / self.width() * self.duration))

    def _start(self) -> float:
        return self.crop_start or 0.0

    def _end(self) -> float:
        return self.crop_end if self.crop_end is not None else self.duration

    def _reference_level(self) -> float:
        if self.peaks is None or not len(self.peaks):
            return 1.0
        if getattr(self, "_ref_for", None) is not self.peaks:
            amp = np.abs(self.peaks.astype(np.float32)).max(axis=1) / 32768.0
            self._ref = max(0.02, float(np.percentile(amp, 99)))
            self._ref_for = self.peaks
        return self._ref

    def _columns_for_width(self) -> np.ndarray | None:
        if self.peaks is None or not len(self.peaks) or self.width() <= 0:
            return None
        key = (self.width(), id(self.peaks))
        if self._columns is not None and self._cache_key == key:
            return self._columns
        n = len(self.peaks)
        w = self.width()
        edges = np.linspace(0, n, w + 1).astype(int)
        lo = np.minimum.reduceat(self.peaks[:, 0], np.minimum(edges[:-1], n - 1))
        hi = np.maximum.reduceat(self.peaks[:, 1], np.minimum(edges[:-1], n - 1))
        self._columns = np.stack([lo, hi], axis=1).astype(np.float32) / 32768.0
        self._cache_key = key
        return self._columns

    # ---- painting ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme.current()
        rect = self.rect()
        surface, ink, accent = QColor(t.surface), QColor(t.ink), QColor(t.accent)
        p.fillRect(rect, surface)
        mid = rect.height() / 2
        cols = self._columns_for_width()
        if cols is None:
            p.setPen(QPen(theme.color("muted", 0.35), 1, Qt.PenStyle.DashLine))
            p.drawLine(0, int(mid), rect.width(), int(mid))
            if self.placeholder:
                p.setPen(QColor(t.muted))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.placeholder)
            p.end()
            return
        played_x = self._x(self.position)
        amp = rect.height() / 2 - 4
        # Normalize to this recording's loud parts, then compress gently so quiet speech stays visible
        # without loud audio turning into a solid block.
        ref = self._reference_level()
        scaled = np.clip(cols / ref, -1.0, 1.0)
        scaled = np.sign(scaled) * np.abs(scaled) ** 0.8
        played = QLinearGradient(0, mid - amp, 0, mid + amp)
        played.setColorAt(0.0, QColor(t.foam))
        played.setColorAt(0.5, accent)
        played.setColorAt(1.0, QColor(t.accent_deep))
        rest = theme.color("accent", 0.28 if not t.dark else 0.32)
        p.setPen(Qt.PenStyle.NoPen)
        step = BAR_STEP
        for x0 in range(0, len(scaled), step):
            seg = scaled[x0:x0 + step]
            lo, hi = float(seg[:, 0].min()), float(seg[:, 1].max())
            top, bottom = mid - max(hi, 0.02) * amp, mid - min(lo, -0.02) * amp
            p.setBrush(played if x0 <= played_x else rest)
            p.drawRoundedRect(QRectF(x0, top, step - 1, bottom - top), 1, 1)
        # Part boundaries of a linked set
        if self.dividers:
            p.setFont(theme.display_font(0.75, QFont.Weight.Bold))
            for k, tm in enumerate([0.0, *self.dividers]):
                x = self._x(tm)
                if k:
                    p.setPen(QPen(theme.color("ink", 0.45), 1, Qt.PenStyle.DashLine))
                    p.drawLine(QPointF(x, 0), QPointF(x, rect.height()))
                p.setPen(QColor(t.muted))
                p.drawText(QRectF(x + 4, rect.height() - 16, 30, 14), Qt.AlignmentFlag.AlignLeft, str(k + 1))
        # Shade outside the crop
        shade = QColor(surface)
        shade.setAlpha(200)
        if not self.editable:
            pass
        elif self.crop_start:
            p.fillRect(QRectF(0, 0, self._x(self.crop_start), rect.height()), shade)
        if self.crop_end is not None and self.crop_end < self.duration:
            xe = self._x(self.crop_end)
            p.fillRect(QRectF(xe, 0, rect.width() - xe, rect.height()), shade)
        # Capture interruptions: small amber notches
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.amber))
        for tm in self.gaps:
            x = self._x(tm)
            p.drawPolygon([QPointF(x - 4, 0), QPointF(x + 4, 0), QPointF(x, 6)])
        # The user's markers: a coral flag with a hairline through the wave
        coral = QColor(t.coral_deep)
        line = QColor(coral)
        line.setAlpha(150)
        for m in self.markers:
            x = self._x(m["at"])
            # A marker just added drops in from above with a small bounce.
            dy = -14 * (1 - self._drop_p) if m["at"] == self._drop_at else 0.0
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(x, 9 + max(0.0, dy)), QPointF(x, rect.height()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(coral)
            p.drawPolygon([QPointF(x - 5.5, dy), QPointF(x + 5.5, dy), QPointF(x + 5.5, 7 + dy),
                           QPointF(x, 11 + dy), QPointF(x - 5.5, 7 + dy)])
        # Crop handles (always drawn subtly at the edges so they are discoverable)
        for which, tm in (("start", self._start()), ("end", self._end())) if self.editable else ():
            x = self._x(tm)
            active = (which == "start" and self.crop_start) or (which == "end" and self.crop_end is not None)
            c = QColor(t.accent_deep) if active else theme.color("muted", 0.4)
            x = min(max(x, 1), rect.width() - 1)
            if active:
                p.setPen(QPen(c, 2))
                p.drawLine(QPointF(x, 0), QPointF(x, rect.height()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x - 6 if which == "end" else x, rect.height() / 2 - 12, 6, 24), 3, 3)
        # Playhead: a line with a knob
        p.setPen(QPen(ink, 2))
        p.drawLine(QPointF(played_x, 4), QPointF(played_x, rect.height()))
        p.setPen(QPen(surface, 2))
        p.setBrush(ink)
        p.drawEllipse(QPointF(played_x, 5), 4.5, 4.5)
        if self.hasFocus():
            p.setPen(QPen(theme.color("accent", 0.5), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.end()

    # ---- interaction ----
    def _handle_at(self, x: float) -> str | None:
        if self.duration <= 0 or not self.editable:
            return None
        for which, t in (("start", self._start()), ("end", self._end())):
            if abs(self._x(t) - x) <= HANDLE_GRAB_PX:
                return which
        return None

    def _marker_at(self, x: float, y: float | None = None) -> int:
        """Index of the user's marker under x (the flag at the top is easiest to grab), or -1."""
        if self.duration <= 0 or not self.editable:
            return -1
        reach = 7 if y is None or y < 14 else 4
        best, dist = -1, reach + 1
        for i, m in enumerate(self.markers):
            d = abs(self._x(m["at"]) - x)
            if d <= reach and d < dist:
                best, dist = i, d
        return best

    def mouseMoveEvent(self, e: QMouseEvent):
        x = e.position().x()
        if self._drag == "marker":
            t = self._t(x)
            if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier) and self.peaks is not None:
                t = peaks_mod.snap(self.peaks, t)
            self.markers[self._drag_marker]["at"] = round(t, 2)
            self.update()
            return
        if self._drag in ("start", "end"):
            t = self._t(x)
            if not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier) and self.peaks is not None:
                t = peaks_mod.snap(self.peaks, t)
            if self._drag == "start":
                self.crop_start = None if t <= 0.05 else min(t, self._end() - 0.5)
            else:
                self.crop_end = None if t >= self.duration - 0.05 else max(t, self._start() + 0.5)
            self.update()
        elif self._drag == "seek":
            self.seek_requested.emit(self._t(x))
        else:
            k = self._marker_at(x, e.position().y())
            if k >= 0:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                note = self.markers[k].get("note") or "Marker"
                QToolTip.showText(e.globalPosition().toPoint(), f"{fmt_duration(self.markers[k]['at'])}  {note}", self)
                return
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._handle_at(x) else Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
            return
        k = self._marker_at(e.position().x(), e.position().y())
        if k >= 0 and not self._handle_at(e.position().x()):
            self._drag, self._drag_marker = "marker", k
            return
        h = self._handle_at(e.position().x())
        if h:
            self._drag = h
            self._last_handle = h
        else:
            self._drag = "seek"
            self.seek_requested.emit(self._t(e.position().x()))

    def mouseReleaseEvent(self, e: QMouseEvent):
        if self._drag in ("start", "end"):
            self.crop_changed.emit(self.crop_start, self.crop_end)
        elif self._drag == "marker":
            self.markers.sort(key=lambda m: m["at"])
            self.markers_edited.emit(self.markers)
        self._drag = None

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and self.duration > 0 and self.editable:
            self.add_marker(self._t(e.position().x()))
        else:
            super().mouseDoubleClickEvent(e)

    def add_marker(self, t: float):
        at = round(max(0.0, min(self.duration, t)), 2)
        self.markers.append({"at": at, "note": ""})
        self.markers.sort(key=lambda m: m["at"])
        self._drop(at)
        self.update()
        self.markers_edited.emit(self.markers)

    def contextMenuEvent(self, e):
        k = self._marker_at(e.pos().x(), e.pos().y())
        if k < 0:
            return
        m = QMenu(self)
        m.addAction(icon("rename"), "Edit note…", lambda: self._edit_note(k))
        m.addAction(icon("delete"), "Remove marker", lambda: self.remove_marker(k))
        m.exec(e.globalPos())

    def _edit_note(self, k: int):
        text, ok = QInputDialog.getText(self, "Marker note", "Note:", text=self.markers[k].get("note", ""))
        if ok:
            self.markers[k]["note"] = text.strip()
            self.markers_edited.emit(self.markers)

    def remove_marker(self, k: int):
        del self.markers[k]
        self.update()
        self.markers_edited.emit(self.markers)

    def keyPressEvent(self, e: QKeyEvent):
        key, mods = e.key(), e.modifiers()
        if self.duration <= 0:
            return super().keyPressEvent(e)
        if not self.editable and (key in (Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight)
                                  or mods & Qt.KeyboardModifier.ControlModifier):
            return super().keyPressEvent(e)
        if key == Qt.Key.Key_BracketLeft:
            self._set_handle("start", self.position)
        elif key == Qt.Key.Key_BracketRight:
            self._set_handle("end", self.position)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and mods & Qt.KeyboardModifier.ControlModifier:
            step = NUDGE_COARSE if mods & Qt.KeyboardModifier.ShiftModifier else NUDGE_FINE
            step = -step if key == Qt.Key.Key_Left else step
            cur = self._start() if self._last_handle == "start" else self._end()
            self._set_handle(self._last_handle, cur + step)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = 1.0 if mods & Qt.KeyboardModifier.ShiftModifier else 5.0
            self.seek_requested.emit(max(0.0, min(self.duration, self.position + (-step if key == Qt.Key.Key_Left else step))))
        elif key == Qt.Key.Key_Home:
            self.seek_requested.emit(self._start())
        else:
            super().keyPressEvent(e)

    def _set_handle(self, which: str, t: float):
        t = max(0.0, min(self.duration, t))
        self._last_handle = which
        if which == "start":
            self.crop_start = None if t <= 0.05 else min(t, self._end() - 0.5)
        else:
            self.crop_end = None if t >= self.duration - 0.05 else max(t, self._start() + 0.5)
        self.update()
        self.crop_changed.emit(self.crop_start, self.crop_end)

    def sizeHint(self) -> QSize:
        return QSize(400, 96)

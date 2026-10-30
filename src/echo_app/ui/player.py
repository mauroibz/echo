"""Player: waveform with crop handles, playback controls, export."""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu,
                               QSizePolicy, QSlider, QToolButton, QToolTip, QVBoxLayout, QWidget)

from ..audio import peaks as peaks_mod
from ..audio.playback import MAX_VOLUME, Playback, SetPlayback
from ..library import READY, Recording
from . import theme
from .common import fmt_date, fmt_duration, fmt_length, icon, run_task

log = logging.getLogger(__name__)

HANDLE_GRAB_PX = 7
BAR_STEP = 3  # waveform bar pitch in pixels (2 px bar, 1 px gap)
NUDGE_FINE = 0.1
NUDGE_COARSE = 1.0


def statistics(rec: Recording) -> str:
    """"1,234 words · 142 words a minute · 18% silence" from the transcript, or ""."""
    t = rec.transcript()
    if not t or not t.get("segments"):
        return ""
    words = len(rec.text().split())
    speech = sum(max(0.0, float(s.get("end", 0)) - float(s.get("start", 0))) for s in t["segments"] if s.get("text"))
    start, end = rec.effective_span()
    span = (end if end is not None else (rec.meta.duration or 0)) - start
    parts = [f"{words:,} words"]
    if speech > 0:
        parts.append(f"{round(words / speech * 60)} words a minute")
    if span > 0 and speech <= span:
        parts.append(f"{round(100 * (1 - speech / span))}% silence")
    return "  ·  ".join(parts)


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
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(x, 9), QPointF(x, rect.height()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(coral)
            p.drawPolygon([QPointF(x - 5.5, 0), QPointF(x + 5.5, 0), QPointF(x + 5.5, 7), QPointF(x, 11),
                           QPointF(x - 5.5, 7)])
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
        self.markers.append({"at": round(max(0.0, min(self.duration, t)), 2), "note": ""})
        self.markers.sort(key=lambda m: m["at"])
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


class PlayerPanel(QWidget):
    renamed = Signal(str, str)  # recording id, new title
    set_renamed = Signal(str, str)  # set id, new title
    markers_changed = Signal(str)  # recording id
    meta_changed = Signal(str)  # recording id whose tags or notes changed
    span_finished = Signal()  # a passage started with play_span reached its end
    crop_saved = Signal(str)
    export_requested = Signal()
    position_changed = Signal(float)
    message = Signal(str)

    SPEEDS = (1.0, 1.25, 1.5, 2.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rec: Recording | None = None
        self.linked = None  # the LinkedSet shown instead of a recording
        self.parts: list = []  # its sets.Part timeline
        self._loaded_sha = None
        self._span: tuple[float, float] | None = None
        self._rec_player = Playback()
        self._set_player = SetPlayback()
        self.player = self._rec_player
        self.volumes: dict[str, float] = {}  # recording or set id -> volume, only those not at 100%
        self._build()
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self.set_recording(None)

    def _build(self):
        """The parts, in three places the window lays out: `header` (title, one line, tags), `dock`
        (playback along the bottom) and the pieces of Details (`context`, `notes`, `file_info`,
        `stats`). The panel itself is not shown."""
        self.header = QWidget()
        hl = QVBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        self.title = QLineEdit()
        self.title.setFrame(False)
        self.title.setObjectName("title")
        self.title.setFont(theme.display_font(1.9, QFont.Weight.ExtraBold))
        self.title.setPlaceholderText("Untitled")
        self.title.setToolTip("Rename (F2)")
        self.title.setAccessibleName("Title")
        self.title.editingFinished.connect(self._commit_title)
        hl.addWidget(self.title)
        line = QHBoxLayout()
        line.setContentsMargins(5, 0, 0, 0)
        line.setSpacing(12)
        self.subtitle = QLabel("")
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        theme.set_role(self.subtitle, dim=True)
        line.addWidget(self.subtitle)
        from .tags import NotesEdit, TagEditor

        self.tags = TagEditor()
        self.tags.changed.connect(self._commit_tags)
        line.addWidget(self.tags, 1)
        hl.addLayout(line)

        self.context = QLineEdit()
        self.context.setObjectName("context")
        self.context.setPlaceholderText("Who is speaking, what about (optional)")
        self._context_tip = ("Used as context when this recording is transcribed, together with the dictionary.\n"
                             "For example: Entrevista con Lucía sobre PipeWire")
        self.context.setToolTip(self._context_tip)
        self.context.setAccessibleName("Who is speaking, what about")
        self.context.editingFinished.connect(self._commit_context)
        self.notes = NotesEdit()
        self.notes.edited.connect(self._commit_notes)
        self.file_info = QLabel("")
        self.file_info.setWordWrap(True)
        self.file_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stats = QLabel("")
        self.stats.setWordWrap(True)

        self.dock = QWidget()
        self.dock.setObjectName("dock")
        row = QHBoxLayout(self.dock)
        row.setContentsMargins(20, 10, 16, 10)
        row.setSpacing(12)
        self.play_btn = QToolButton()
        self.play_btn.setObjectName("play")
        self.play_btn.setIcon(icon("play", "on_accent"))
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.setAccessibleName("Play")
        self.play_btn.clicked.connect(self.toggle_play)
        row.addWidget(self.play_btn)
        self.time = QLabel("0:00")
        self.time.setFont(theme.display_font(0.95, QFont.Weight.Bold, tabular=True))
        self.time.setMinimumWidth(self.time.fontMetrics().horizontalAdvance("0:00:00") + 4)
        row.addWidget(self.time)
        self.wave = WaveformView()
        self.wave.setMinimumHeight(44)
        self.wave.setMaximumHeight(52)
        self.wave.seek_requested.connect(self.seek)
        self.wave.crop_changed.connect(self._crop_changed)
        self.wave.markers_edited.connect(self._markers_edited)
        row.addWidget(self.wave, 1)
        self.total = QLabel("0:00")
        self.total.setFont(theme.display_font(0.95, QFont.Weight.DemiBold, tabular=True))
        theme.set_role(self.total, dim=True)
        row.addWidget(self.total)
        self.crop_label = QLabel("")
        theme.set_role(self.crop_label, dim=True)
        row.addWidget(self.crop_label)
        self.clear_crop_btn = QToolButton()
        self.clear_crop_btn.setIcon(icon("clear", "muted"))
        self.clear_crop_btn.setToolTip("Clear the crop")
        self.clear_crop_btn.setAccessibleName("Clear crop")
        self.clear_crop_btn.clicked.connect(self.clear_crop)
        row.addWidget(self.clear_crop_btn)
        # Speed: one button that steps through the speeds (its menu lists them); the combo box
        # holds the value.
        self.speed = QComboBox(self)
        for s in self.SPEEDS:
            self.speed.addItem(f"{s:g}×", s)
        self.speed.hide()
        self.speed.currentIndexChanged.connect(lambda _i: self.player.set_speed(self.speed.currentData()))
        self.speed_btn = QToolButton()
        self.speed_btn.setObjectName("pill")
        self.speed_btn.setFont(theme.display_font(0.9, QFont.Weight.Bold, tabular=True))
        self.speed_btn.setToolTip("Playback speed: click for the next one")
        self.speed_btn.setAccessibleName("Playback speed")
        self.speed_btn.clicked.connect(lambda: self.speed.setCurrentIndex((self.speed.currentIndex() + 1)
                                                                          % self.speed.count()))
        self.speed.currentIndexChanged.connect(lambda _i: self.speed_btn.setText(self.speed.currentText()))
        self.speed_btn.setText(self.speed.currentText())
        row.addWidget(self.speed_btn)
        # Volume, for quiet recordings: up to 400% (a limiter keeps the boost from clipping), in a
        # popup. Each change restarts the pipeline, so a drag applies once the slider settles.
        self.volume_btn = QToolButton()
        self.volume_btn.setIcon(icon("volume", "muted"))
        self.volume_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.volume_btn.setFont(theme.display_font(0.85, QFont.Weight.Bold, tabular=True))
        self.volume_btn.setToolTip("Volume")
        self.volume_btn.setAccessibleName("Volume")
        self.volume_btn.clicked.connect(self._open_volume)
        row.addWidget(self.volume_btn)
        self.volume_popup = QFrame(self, Qt.WindowType.Popup)
        self.volume_popup.setObjectName("popup")
        vl = QHBoxLayout(self.volume_popup)
        vl.setContentsMargins(14, 10, 10, 10)
        vl.setSpacing(8)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, round(MAX_VOLUME * 100))
        self.volume.setSingleStep(5)
        self.volume.setPageStep(10)
        self.volume.setValue(100)
        self.volume.setFixedWidth(180)
        self.volume.setToolTip("Volume. Above 100% boosts quiet recordings; the audio file is not changed.\n"
                               "Remembered for each recording. Double-click for 100%.")
        self.volume.setAccessibleName("Volume")
        self.volume.valueChanged.connect(self._volume_moved)
        self.volume.installEventFilter(self)
        vl.addWidget(self.volume)
        self.volume_label = QToolButton()
        self.volume_label.setText("100%")
        self.volume_label.setFont(theme.display_font(0.85, QFont.Weight.Bold, tabular=True))
        self.volume_label.setMinimumWidth(self.volume_label.fontMetrics().horizontalAdvance("400%") + 12)
        self.volume_label.setToolTip("Back to 100%")
        self.volume_label.setAccessibleName("Reset volume to 100%")
        self.volume_label.clicked.connect(lambda: self.volume.setValue(100))
        vl.addWidget(self.volume_label)
        self._volume_timer = QTimer(self, singleShot=True, interval=150, timeout=self._apply_volume)
        self.export_btn = QToolButton(self)  # exporting is in the header's Export menu
        self.export_btn.hide()
        self.export_btn.clicked.connect(self.export_requested.emit)

    def _open_volume(self):
        self.volume_popup.adjustSize()
        at = self.volume_btn.mapToGlobal(self.volume_btn.rect().topRight())
        self.volume_popup.move(at.x() - self.volume_popup.width(), at.y() - self.volume_popup.height() - 6)
        self.volume_popup.show()
        self.volume.setFocus()

    # ---- recording ----
    def _leave_set(self):
        if self.linked is None:
            return
        self._set_player.stop()
        self._rec_player.set_speed(self._set_player.speed)
        self.player = self._rec_player
        self.linked, self.parts = None, []
        self.wave.editable, self.wave.dividers = True, []
        for w in (self.tags, self.notes):
            w.show()
        self.title.setToolTip("Rename (F2)")
        self.context.setToolTip(self._context_tip)

    def set_linked(self, linked, parts: list[Recording]):
        """Show a linked set: its title, its parts on one timeline, read-only waveform."""
        from .. import sets

        same = self.linked is not None and linked.id == self.linked.id
        timeline = sets.timeline(parts)
        sig = [(p.rec.id, p.rec.meta.sha256, p.start, p.length) for p in timeline]
        if self.linked is None:
            self.player.stop()
            self._set_player.set_speed(self._rec_player.speed)
        self.rec = None
        self.linked = linked
        self.player = self._set_player
        for w in (self.tags, self.notes, self.clear_crop_btn):
            w.hide()
        self.crop_label.setText("")
        self.title.setEnabled(True)
        self.title.setToolTip("Rename this set (F2)")
        self.context.setToolTip("Used as context when each part is transcribed, together with the dictionary.")
        if not self.title.hasFocus():
            self.title.setText(linked.title)
        contexts = {r.meta.context_line for r in parts}
        if not self.context.hasFocus():
            self.context.setText(contexts.pop() if len(contexts) == 1 else "")
        self.context.setEnabled(True)
        first, last = parts[0].meta.created, parts[-1].meta.created
        span = fmt_date(first) + (f" to {fmt_date(last).split(' ')[-1]}" if first[:10] == last[:10] else
                                  f" to {fmt_date(last)}")
        self.subtitle.setText(f"{span} · {sets.summary(linked, parts)}")
        self.file_info.setText("")
        self.stats.setText("")
        playable = any(p.rec.audio_path is not None and p.rec.audio_path.exists() for p in timeline)
        for w in (self.play_btn, self.speed_btn, self.volume_btn, self.volume, self.volume_label, self.wave):
            w.setEnabled(playable)
        self._show_volume()
        if same and sig == getattr(self, "_set_sig", None):
            self.wave.markers = self._set_markers(timeline)
            self.wave.update()
            return
        self._set_sig = sig
        self.parts = timeline
        self._set_player.load(timeline)
        self._sync_play_icon()
        self.wave.editable = False
        self.wave.dividers = [p.offset for p in timeline[1:]]
        self.wave.placeholder = "Drawing waveform…"
        self.wave.set_recording(sets.total(timeline), None, None, (), self._set_markers(timeline))
        self.wave.set_peaks(None)
        sid = linked.id
        jobs = [(p.rec.audio_path, p.rec.meta.sha256, p.start, p.length, bool(p.rec.meta.tracks))
                for p in timeline]

        def compute():
            chunks = []
            for path, key, start, length, mix in jobs:
                n = int(round(length * peaks_mod.BUCKETS_PER_SECOND))
                try:
                    pk = peaks_mod.compute(path, key, mix) if path is not None and path.exists() else None
                except Exception:  # noqa: BLE001 - a part without a waveform still has its place
                    pk = None
                a = int(round(start * peaks_mod.BUCKETS_PER_SECOND))
                chunk = pk[a:a + n] if pk is not None else np.zeros((0, 2), dtype=np.int16)
                if len(chunk) < n:
                    chunk = np.concatenate([chunk, np.zeros((n - len(chunk), 2), dtype=chunk.dtype)])
                chunks.append(chunk)
            return np.concatenate(chunks) if chunks else None

        run_task(compute, on_done=lambda pk: self._set_peaks_ready(sid, pk),
                 on_error=lambda m: log.warning("waveform failed: %s", m))
        self._update_time()

    @staticmethod
    def _set_markers(timeline) -> list[dict]:
        out = []
        for p in timeline:
            for m in p.rec.meta.markers:
                if p.start <= m["at"] <= p.start + p.length:
                    out.append({"at": p.to_set(m["at"]), "note": m.get("note") or ""})
        return out

    def _set_peaks_ready(self, sid: str, pk):
        if self.linked is not None and self.linked.id == sid:
            self.wave.set_peaks(pk)

    def set_recording(self, rec: Recording | None):
        self._leave_set()
        same = rec is not None and self.rec is not None and rec.id == self.rec.id
        self.rec = rec
        playable = rec is not None and rec.meta.state == READY and rec.audio_path is not None and rec.audio_path.exists()
        for w in (self.play_btn, self.speed_btn, self.volume_btn, self.volume, self.volume_label, self.export_btn,
                  self.wave):
            w.setEnabled(playable)
        self._show_volume()
        self.title.setEnabled(rec is not None)
        for w in (self.context, self.tags, self.notes):
            w.setEnabled(rec is not None)
        if rec is None:
            self.player.load(None, 0)
            self._sync_play_icon()
            self._loaded_sha = None
            self.title.setText("")
            self.context.setText("")
            self.tags.set_tags([])
            self.notes.set_text("")
            self.subtitle.setText("")
            self.file_info.setText("")
            self.stats.setText("")
            self.wave.placeholder = ""
            self.wave.set_recording(0, None, None)
            self.wave.set_peaks(None)
            self._update_crop_label()
            self._update_time()
            return
        if not self.title.hasFocus():
            self.title.setText(rec.meta.title)
        if not self.context.hasFocus():
            self.context.setText(rec.meta.context_line)
        self.tags.set_tags(rec.meta.tags)
        self.notes.set_text(rec.meta.notes)
        bits = [fmt_date(rec.meta.created)]
        if rec.meta.duration:
            bits.append(fmt_length(rec.meta.duration))
        n = len(rec.speaker_numbers()) if not rec.meta.speakers_off else 0
        if n > 1:
            bits.append(f"{n} speakers")
        self.subtitle.setText(" · ".join(bits))
        facts = [rec.meta.source or rec.meta.audio or ""]
        if rec.meta.recovered:
            facts.append("Recovered after a crash")
        interruptions = [g for g in rec.meta.gaps if g.get("kind") == "interruption"]
        if interruptions:
            facts.append(f"{len(interruptions)} capture interruption{'s' if len(interruptions) > 1 else ''}")
        self.file_info.setText("\n".join(f for f in facts if f))
        self.stats.setText(statistics(rec).replace("  ·  ", "\n"))
        if same and self._loaded_sha == rec.meta.sha256 and playable:
            self.wave.crop_start, self.wave.crop_end = rec.meta.crop_start, rec.meta.crop_end
            if self.wave._drag != "marker":
                self.wave.markers = [dict(m) for m in rec.meta.markers]
            self._update_crop_label()
            self.wave.update()
            return
        self.player.stop()
        self._sync_play_icon()
        if not playable:
            self.player.load(None, 0)
            self._loaded_sha = None
            self.wave.placeholder = ("Recording in progress" if rec.meta.state == "recording"
                                     else rec.meta.error or "No audio")
            self.wave.set_recording(0, None, None)
            self.wave.set_peaks(None)
            self._update_crop_label()
            self._update_time()
            return
        self._loaded_sha = rec.meta.sha256
        self.player.load(rec.audio_path, rec.meta.duration or 0, bool(rec.meta.tracks))
        if rec.meta.crop_start:
            self.player.seek(rec.meta.crop_start)
        gaps = [g["at"] for g in interruptions if "at" in g]
        self.wave.placeholder = "Drawing waveform…"
        self.wave.set_recording(rec.meta.duration or 0, rec.meta.crop_start, rec.meta.crop_end, gaps,
                                rec.meta.markers)
        self.wave.set_peaks(None)
        rid, path, key = rec.id, rec.audio_path, rec.meta.sha256
        run_task(peaks_mod.compute, path, key, bool(rec.meta.tracks),
                 on_done=lambda pk: self._peaks_ready(rid, pk),
                 on_error=lambda m: log.warning("waveform failed: %s", m))
        self._update_crop_label()
        self._update_time()

    def _peaks_ready(self, rid: str, pk):
        if self.rec is not None and self.rec.id == rid:
            self.wave.set_peaks(pk)

    def _commit_title(self):
        if self.linked is not None:
            new = self.title.text().strip()
            if not new:
                self.title.setText(self.linked.title)
            elif new != self.linked.title:
                self.linked.title = new
                self.set_renamed.emit(self.linked.id, new)
            return
        if self.rec is None:
            return
        new = self.title.text().strip()
        if not new:
            self.title.setText(self.rec.meta.title)
            return
        if new != self.rec.meta.title:
            self.rec.update(title=new, title_auto=False)  # the user's title is never replaced
            self.renamed.emit(self.rec.id, new)

    def _commit_tags(self, tags: list):
        if self.rec is not None:
            self.tags.set_tags(self.rec.set_tags(tags))
            self.meta_changed.emit(self.rec.id)

    def _commit_notes(self, text: str):
        if self.rec is not None and text != self.rec.meta.notes:
            self.rec.update(notes=text)
            self.meta_changed.emit(self.rec.id)

    def _commit_context(self):
        line = " ".join(self.context.text().split())
        if self.linked is not None:
            # A burst has the same people throughout: the line goes to every part.
            for p in self.parts:
                if p.rec.meta.context_line != line:
                    p.rec.update(context_line=line)
            return
        if self.rec is None:
            return
        if line != self.rec.meta.context_line:
            self.rec.update(context_line=line)

    def focus_title(self):
        self.title.setFocus()
        self.title.selectAll()

    # ---- crop ----
    def _crop_changed(self, start, end):
        if self.rec is None or self.linked is not None:
            return
        self.rec.update(crop_start=round(start, 2) if start else None,
                        crop_end=round(end, 2) if end is not None else None)
        self._update_crop_label()
        self.crop_saved.emit(self.rec.id)

    def _markers_edited(self, markers: list):
        if self.rec is None:
            return
        self.rec.set_markers(markers)
        self.markers_changed.emit(self.rec.id)

    def add_marker_at_playhead(self):
        if self.linked is not None:
            self.message.emit("Markers belong to one part: select the part to add one.")
            return
        if self.rec is None or not self.wave.isEnabled():
            return
        at = self.player.position()
        self.wave.add_marker(at)
        self.message.emit(f"Marker at {fmt_duration(at)}. Right-click it on the waveform to add a note.")

    def jump_marker(self, direction: int):
        """Seek to the next (1) or previous (-1) marker, and keep playing if playing."""
        markers = self.wave.markers if self.linked is not None else (self.rec.meta.markers if self.rec else [])
        if not markers:
            return
        pos = self.player.position()
        ats = [m["at"] for m in markers]
        if direction > 0:
            target = next((a for a in ats if a > pos + 0.25), None)
        else:
            # Pressed again right after a jump, it goes one further back, as in a music player.
            target = next((a for a in reversed(ats) if a < pos - 1.5), None)
        if target is not None:
            self.seek(target)

    def clear_crop(self):
        self.wave.crop_start = self.wave.crop_end = None
        self.wave.update()
        self._crop_changed(None, None)

    def _update_crop_label(self):
        rec = self.rec
        cropped = rec is not None and (rec.meta.crop_start or rec.meta.crop_end is not None)
        self.clear_crop_btn.setVisible(bool(cropped))
        if cropped:
            s = rec.meta.crop_start or 0
            e = rec.meta.crop_end if rec.meta.crop_end is not None else (rec.meta.duration or 0)
            self.crop_label.setText(f"Crop {fmt_duration(s)}–{fmt_duration(e)}")
        else:
            self.crop_label.setText("")
        self.crop_label.setVisible(bool(cropped))

    # ---- playback ----
    def _shown(self) -> bool:
        return self.rec is not None or self.linked is not None

    def play_span(self, start: float, end: float) -> None:
        """Play one passage and stop at its end (editing with the audio)."""
        if not self._shown() or not self.play_btn.isEnabled():
            return
        self._span = (start, end)
        self.player.play(start, end)
        self._sync_play_icon()

    def stop_span(self) -> None:
        self._span = None
        if self.player.playing:
            self.player.pause()
        self._sync_play_icon()

    def toggle_play(self):
        if not self._shown() or not self.play_btn.isEnabled():
            return
        self._span = None
        if self.player.playing:
            self.player.pause()
        elif self.linked is not None:
            self.player.play(None, None)  # from the playhead; from the start once at the end
        else:
            start, end = self.rec.effective_span()
            pos = self.player.position()
            if pos < start - 0.05 or (end is not None and pos >= end - 0.05) or \
                    (self.player.duration and pos >= self.player.duration - 0.05):
                pos = start
            self.player.play(pos, end)
        self._sync_play_icon()

    def seek(self, sec: float):
        if not self._shown():
            return
        self.player.seek(sec)
        self.wave.set_position(sec)
        self._update_time()
        self.position_changed.emit(sec)

    def _sync_play_icon(self):
        playing = self.player.playing
        self.play_btn.setIcon(icon("pause" if playing else "play", "on_accent"))
        self.play_btn.setAccessibleName("Pause" if playing else "Play")
        if playing:
            self._timer.start()
        else:
            self._timer.stop()
            self._tick()

    def _tick(self):
        if not self._shown():
            return
        if self.player.poll():
            self._sync_play_icon()
            if self.player.error:
                self.message.emit(f"Playback failed: {self.player.error}")
            elif self._span is not None:
                self._span = None
                self.span_finished.emit()
        pos = self.player.position()
        self.wave.set_position(pos)
        self._update_time()
        self.position_changed.emit(pos)

    def _update_time(self):
        dur = (self.rec.meta.duration if self.rec else 0) or self.player.duration
        if self.linked is not None:
            dur = self.player.duration
        self.time.setText(fmt_duration(self.player.position()))
        self.total.setText(fmt_duration(dur))

    def speed_value(self) -> float:
        return self.speed.currentData()

    def set_speed(self, value: float):
        idx = self.speed.findData(value)
        if idx >= 0:
            self.speed.setCurrentIndex(idx)

    # ---- volume ----
    def _volume_key(self) -> str | None:
        if self.linked is not None:
            return self.linked.id
        return self.rec.id if self.rec is not None else None

    def _show_volume(self):
        """Put the shown recording's own volume on the slider and the player."""
        self._volume_timer.stop()
        value = self.volumes.get(self._volume_key(), 1.0)
        if self.volume.value() != round(value * 100):
            self.volume.blockSignals(True)
            self.volume.setValue(round(value * 100))
            self.volume.blockSignals(False)
        self.volume_label.setText(f"{self.volume.value()}%")
        self._show_volume_btn()
        self.player.set_volume(value)

    def _show_volume_btn(self):
        pct = self.volume.value()
        self.volume_btn.setText("" if pct == 100 else f"{pct}%")

    def _volume_moved(self, pct: int):
        # Stored at once, so a refresh of the same recording during a drag keeps the new value.
        self.volume_label.setText(f"{pct}%")
        self._show_volume_btn()
        key = self._volume_key()
        if key is not None:
            if pct == 100:
                self.volumes.pop(key, None)
            else:
                self.volumes[key] = pct / 100
        self._volume_timer.start()

    def _apply_volume(self):
        self.player.set_volume(self.volume.value() / 100)

    def volume_value(self) -> float:
        return self.volume.value() / 100

    def eventFilter(self, obj, event):
        if obj is self.volume and event.type() == QEvent.Type.MouseButtonDblClick:
            self.volume.setValue(100)
            return True
        return super().eventFilter(obj, event)

    def is_playing(self) -> bool:
        return self.player.playing

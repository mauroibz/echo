"""Player: waveform with crop handles, playback controls, export."""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from ..audio import peaks as peaks_mod
from ..audio.playback import Playback
from ..library import READY, Recording
from . import theme
from .common import fmt_date, fmt_duration, icon, run_task

log = logging.getLogger(__name__)

HANDLE_GRAB_PX = 7
BAR_STEP = 3  # waveform bar pitch in pixels (2 px bar, 1 px gap)
NUDGE_FINE = 0.1
NUDGE_COARSE = 1.0


class WaveformView(QWidget):
    seek_requested = Signal(float)
    crop_changed = Signal(object, object)  # start, end (None = unset)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Waveform")
        self.setToolTip("Click to seek. Drag the edges to crop; hold Shift to place freely.\n"
                        "[ and ] set the crop at the playhead; Ctrl+arrows nudge it.")
        self.peaks: np.ndarray | None = None
        self.duration = 0.0
        self.position = 0.0
        self.crop_start: float | None = None
        self.crop_end: float | None = None
        self.markers: list[float] = []
        self.placeholder = ""
        self._drag: str | None = None  # "start" | "end" | "seek"
        self._last_handle = "start"
        self._cache_key = None
        self._columns = None

    # ---- data ----
    def set_recording(self, duration: float, crop_start, crop_end, markers=()):
        self.duration = max(0.0, duration or 0.0)
        self.crop_start, self.crop_end = crop_start, crop_end
        self.markers = list(markers)
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
        # Shade outside the crop
        shade = QColor(surface)
        shade.setAlpha(200)
        if self.crop_start:
            p.fillRect(QRectF(0, 0, self._x(self.crop_start), rect.height()), shade)
        if self.crop_end is not None and self.crop_end < self.duration:
            xe = self._x(self.crop_end)
            p.fillRect(QRectF(xe, 0, rect.width() - xe, rect.height()), shade)
        # Interruption markers
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.amber))
        for tm in self.markers:
            x = self._x(tm)
            p.drawPolygon([QPointF(x - 4, 0), QPointF(x + 4, 0), QPointF(x, 6)])
        # Crop handles (always drawn subtly at the edges so they are discoverable)
        for which, tm in (("start", self._start()), ("end", self._end())):
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
        if self.duration <= 0:
            return None
        for which, t in (("start", self._start()), ("end", self._end())):
            if abs(self._x(t) - x) <= HANDLE_GRAB_PX:
                return which
        return None

    def mouseMoveEvent(self, e: QMouseEvent):
        x = e.position().x()
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
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._handle_at(x) else Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() != Qt.MouseButton.LeftButton or self.duration <= 0:
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
        self._drag = None

    def keyPressEvent(self, e: QKeyEvent):
        key, mods = e.key(), e.modifiers()
        if self.duration <= 0:
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
    crop_saved = Signal(str)
    export_requested = Signal()
    position_changed = Signal(float)
    message = Signal(str)

    SPEEDS = (1.0, 1.25, 1.5, 2.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rec: Recording | None = None
        self._loaded_sha = None
        self.player = Playback()
        self._build()
        self._timer = QTimer(self, interval=40, timeout=self._tick)
        self.set_recording(None)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        self.title = QLineEdit()
        self.title.setFrame(False)
        self.title.setObjectName("title")
        self.title.setFont(theme.display_font(1.65, QFont.Weight.ExtraBold))
        self.title.setPlaceholderText("Untitled")
        self.title.setToolTip("Rename (F2)")
        self.title.setAccessibleName("Title")
        self.title.editingFinished.connect(self._commit_title)
        lay.addWidget(self.title)
        self.subtitle = QLabel("")
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        theme.set_role(self.subtitle, dim=True)
        lay.addWidget(self.subtitle)
        self.context = QLineEdit()
        self.context.setObjectName("context")
        self.context.setFrame(False)
        self.context.setPlaceholderText("Who is speaking, what about (optional, helps transcription)")
        self.context.setToolTip("Used as context when this recording is transcribed, together with the dictionary.\n"
                                "For example: Entrevista con Lucía sobre PipeWire")
        self.context.setAccessibleName("Who is speaking, what about")
        self.context.editingFinished.connect(self._commit_context)
        lay.addWidget(self.context)
        self.wave = WaveformView()
        self.wave.seek_requested.connect(self.seek)
        self.wave.crop_changed.connect(self._crop_changed)
        lay.addWidget(self.wave, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.play_btn = QToolButton()
        self.play_btn.setObjectName("play")
        self.play_btn.setIcon(icon("play", "on_accent"))
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setFixedSize(42, 42)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.setAccessibleName("Play")
        self.play_btn.clicked.connect(self.toggle_play)
        row.addWidget(self.play_btn)
        self.time = QLabel("0:00 / 0:00")
        self.time.setFont(theme.display_font(1.0, QFont.Weight.DemiBold, tabular=True))
        self.time.setMinimumWidth(120)
        row.addWidget(self.time)
        self.speed = QComboBox()
        for s in self.SPEEDS:
            self.speed.addItem(f"{s:g}×", s)
        self.speed.setToolTip("Playback speed")
        self.speed.setAccessibleName("Playback speed")
        self.speed.currentIndexChanged.connect(lambda _i: self.player.set_speed(self.speed.currentData()))
        row.addWidget(self.speed)
        row.addStretch(1)
        self.crop_label = QLabel("")
        row.addWidget(self.crop_label)
        self.clear_crop_btn = QToolButton()
        self.clear_crop_btn.setText("Clear crop")
        self.clear_crop_btn.setIcon(icon("clear"))
        self.clear_crop_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.clear_crop_btn.clicked.connect(self.clear_crop)
        row.addWidget(self.clear_crop_btn)
        self.export_btn = QToolButton()
        self.export_btn.setText("Export audio…")
        self.export_btn.setIcon(icon("export"))
        self.export_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export_btn.clicked.connect(self.export_requested.emit)
        row.addWidget(self.export_btn)
        lay.addLayout(row)

    # ---- recording ----
    def set_recording(self, rec: Recording | None):
        same = rec is not None and self.rec is not None and rec.id == self.rec.id
        self.rec = rec
        playable = rec is not None and rec.meta.state == READY and rec.audio_path is not None and rec.audio_path.exists()
        for w in (self.play_btn, self.speed, self.export_btn, self.wave):
            w.setEnabled(playable)
        self.title.setEnabled(rec is not None)
        self.context.setEnabled(rec is not None)
        if rec is None:
            self.player.load(None, 0)
            self._sync_play_icon()
            self._loaded_sha = None
            self.title.setText("")
            self.context.setText("")
            self.subtitle.setText("")
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
        bits = [fmt_date(rec.meta.created)]
        if rec.meta.duration:
            bits.append(fmt_duration(rec.meta.duration))
        if rec.meta.source:
            bits.append(rec.meta.source)
        if rec.meta.recovered:
            bits.append("recovered after a crash")
        interruptions = [g for g in rec.meta.gaps if g.get("kind") == "interruption"]
        if interruptions:
            bits.append(f"{len(interruptions)} capture interruption{'s' if len(interruptions) > 1 else ''}")
        self.subtitle.setText("  ·  ".join(bits))
        if same and self._loaded_sha == rec.meta.sha256 and playable:
            self.wave.crop_start, self.wave.crop_end = rec.meta.crop_start, rec.meta.crop_end
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
        self.player.load(rec.audio_path, rec.meta.duration or 0)
        if rec.meta.crop_start:
            self.player.seek(rec.meta.crop_start)
        markers = [g["at"] for g in interruptions if "at" in g]
        self.wave.placeholder = "Drawing waveform…"
        self.wave.set_recording(rec.meta.duration or 0, rec.meta.crop_start, rec.meta.crop_end, markers)
        self.wave.set_peaks(None)
        rid, path, key = rec.id, rec.audio_path, rec.meta.sha256
        run_task(peaks_mod.compute, path, key, on_done=lambda pk: self._peaks_ready(rid, pk),
                 on_error=lambda m: log.warning("waveform failed: %s", m))
        self._update_crop_label()
        self._update_time()

    def _peaks_ready(self, rid: str, pk):
        if self.rec is not None and self.rec.id == rid:
            self.wave.set_peaks(pk)

    def _commit_title(self):
        if self.rec is None:
            return
        new = self.title.text().strip()
        if not new:
            self.title.setText(self.rec.meta.title)
            return
        if new != self.rec.meta.title:
            self.rec.update(title=new)
            self.renamed.emit(self.rec.id, new)

    def _commit_context(self):
        if self.rec is None:
            return
        line = " ".join(self.context.text().split())
        if line != self.rec.meta.context_line:
            self.rec.update(context_line=line)

    def focus_title(self):
        self.title.setFocus()
        self.title.selectAll()

    # ---- crop ----
    def _crop_changed(self, start, end):
        if self.rec is None:
            return
        self.rec.update(crop_start=round(start, 2) if start else None,
                        crop_end=round(end, 2) if end is not None else None)
        self._update_crop_label()
        self.crop_saved.emit(self.rec.id)

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

    # ---- playback ----
    def toggle_play(self):
        if self.rec is None or not self.play_btn.isEnabled():
            return
        if self.player.playing:
            self.player.pause()
        else:
            start, end = self.rec.effective_span()
            pos = self.player.position()
            if pos < start - 0.05 or (end is not None and pos >= end - 0.05) or \
                    (self.player.duration and pos >= self.player.duration - 0.05):
                pos = start
            self.player.play(pos, end)
        self._sync_play_icon()

    def seek(self, sec: float):
        if self.rec is None:
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
        if self.rec is None:
            return
        if self.player.poll():
            self._sync_play_icon()
            if self.player.error:
                self.message.emit(f"Playback failed: {self.player.error}")
        pos = self.player.position()
        self.wave.set_position(pos)
        self._update_time()
        self.position_changed.emit(pos)

    def _update_time(self):
        dur = (self.rec.meta.duration if self.rec else 0) or self.player.duration
        self.time.setText(f"{fmt_duration(self.player.position())} / {fmt_duration(dur)}")

    def speed_value(self) -> float:
        return self.speed.currentData()

    def set_speed(self, value: float):
        idx = self.speed.findData(value)
        if idx >= 0:
            self.speed.setCurrentIndex(idx)

    def is_playing(self) -> bool:
        return self.player.playing

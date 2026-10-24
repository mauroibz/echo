"""Recorder controls: source, level meter, listen, record / pause / stop, elapsed time."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QLinearGradient, QPainter, QShortcut
from PySide6.QtWidgets import (QComboBox, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
                               QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget)

from .. import recorder, settings
from ..audio import backend, levels, monitor
from ..audio.backend import INPUT, Source
from ..library import Library
from . import theme
from .common import dot_icon, fmt_duration, icon, run_task

log = logging.getLogger(__name__)

FLOOR_DB = -60.0
WAVE_HEIGHT = 64
# Exact digital silence: a connected microphone with its gain up never produces it.
SILENT_DB = levels.SILENCE_DB + 1
SILENT_AFTER_S = 4.0
NOTE_IDLE_MS = 10_000  # the marker note field closes after this long without typing
SILENT_HINT = ("No sound from this input for {s} seconds. Check that the microphone is connected, "
               "not muted and its gain is up, or pick another input.")


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


class RecorderPanel(QWidget):
    started = Signal(str)  # recording id
    stopped = Signal(str)
    message = Signal(str)  # transient status-bar message
    recording_changed = Signal(bool)

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self.session: recorder.Session | None = None
        self._sources: list[Source] = []
        self._monitor: monitor.LevelMonitor | None = None
        self._listener = monitor.Listener()
        self._busy = False
        self._window_shown = True
        self._silent_since: float | None = None
        self._state = ""
        self._phase, self._swell, self._wave_t = 0.0, 0.0, time.monotonic()
        self._wave_timer = QTimer(self, interval=33, timeout=self._animate)
        self._build()
        self._timer = QTimer(self, interval=100, timeout=self._tick)
        self._timer.start()
        self._sources_loaded = False
        self.reload_sources()

    # ---- layout ----
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, WAVE_HEIGHT - 10)
        lay.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(8)
        self.wordmark = QLabel("echo")
        self.wordmark.setFont(theme.display_font(2.1, QFont.Weight.ExtraBold))
        self.wordmark.setAccessibleName("Echo")
        brand.addWidget(self.wordmark)
        brand.addStretch(1)
        self.state_label = QLabel("")
        self.state_label.setFont(theme.display_font(0.9, QFont.Weight.Bold))
        brand.addWidget(self.state_label)
        lay.addLayout(brand)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.source = SourceCombo()
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source.setMinimumContentsLength(10)
        self.source.setToolTip("Input to record from")
        self.source.setAccessibleName("Input source")
        self.source.aboutToShow.connect(self.reload_sources)
        self.source.activated.connect(self._source_chosen)
        row.addWidget(self.source, 1)
        self.listen = QToolButton()
        self.listen.setIcon(icon("listen", "on_deep"))
        self.listen.setIconSize(QSize(18, 18))
        self.listen.setFixedSize(38, 34)
        self.listen.setCheckable(True)
        self.listen.setToolTip("Listen to this input through your speakers or headphones")
        self.listen.setAccessibleName("Listen to input")
        self.listen.toggled.connect(self._toggle_listen)
        row.addWidget(self.listen)
        try:
            self.listen.setVisible(backend.get().can_listen)
        except backend.BackendMissing:
            self.listen.hide()
        lay.addLayout(row)

        self.meter = LevelMeter()
        lay.addWidget(self.meter)

        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        self.record_btn = QToolButton()
        self.record_btn.setObjectName("record")
        self.record_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.record_btn.setIconSize(QSize(18, 18))
        self.record_btn.setFixedHeight(46)
        self.record_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.clicked.connect(self.toggle_record)
        self._glow = QGraphicsDropShadowEffect(self.record_btn, blurRadius=28, offset=QPointF(0, 6))
        self.record_btn.setGraphicsEffect(self._glow)
        ctl.addWidget(self.record_btn, 1)
        self.pause_btn = QToolButton()
        self.pause_btn.setObjectName("pause")
        self.pause_btn.setIcon(icon("pause", "on_deep"))
        self.pause_btn.setIconSize(QSize(18, 18))
        self.pause_btn.setFixedSize(46, 46)
        self.pause_btn.setToolTip("Pause recording (Ctrl+Shift+R)")
        self.pause_btn.setAccessibleName("Pause recording")
        self.pause_btn.clicked.connect(self.toggle_pause)
        ctl.addWidget(self.pause_btn)
        lay.addLayout(ctl)

        self.elapsed = QLabel("0:00:00")
        self.elapsed.setFont(theme.display_font(2.3, QFont.Weight.Light, tabular=True))
        self.elapsed.setAccessibleName("Recorded time")
        lay.addWidget(self.elapsed)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        theme.set_role(self.warning, warn=True)
        self.warning.hide()
        lay.addWidget(self.warning)

        # After a marker: an optional note, typed without stopping the recording.
        self.note = QLineEdit()
        self.note.setObjectName("markernote")
        self.note.setPlaceholderText("Note for this marker (Enter to save, Esc to skip)")
        self.note.setAccessibleName("Marker note")
        self.note.addAction(icon("bookmark", "on_deep"), QLineEdit.ActionPosition.LeadingPosition)
        self.note.returnPressed.connect(self._save_note)
        self.note.textEdited.connect(lambda _t: self._note_timer.start())
        self.note.hide()
        lay.addWidget(self.note)
        self._note_timer = QTimer(self, singleShot=True, interval=NOTE_IDLE_MS, timeout=self._close_note)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.note, activated=self._close_note,
                        context=Qt.ShortcutContext.WidgetShortcut)
        self._note_esc = esc
        self._update_buttons()

    # ---- waves ----
    def _animate(self):
        now = time.monotonic()
        dt, self._wave_t = min(0.1, now - self._wave_t), now
        live = self.session is not None and self._state != recorder.S_PAUSED
        target = max(0.0, min(1.0, (self.meter._level - FLOOR_DB) / -FLOOR_DB)) if (live or self._monitor) else 0.0
        self._swell += (target - self._swell) * min(1.0, dt * 6)
        self._phase += dt * (0.9 + 2.2 * self._swell)
        self.update(0, self.height() - WAVE_HEIGHT, self.width(), WAVE_HEIGHT)
        # Rest when nothing moves: no input, not recording.
        if not live and self._swell < 0.01 and target == 0.0:
            self._wave_timer.stop()

    def _wake_waves(self):
        if not self._wave_timer.isActive() and self._window_shown:
            self._wave_t = time.monotonic()
            self._wave_timer.start()

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(0, self.height() - WAVE_HEIGHT, self.width(), WAVE_HEIGHT)
        recording = self.session is not None and self._state != recorder.S_PAUSED
        theme.paint_waves(p, r, self._phase, self._swell, theme.color("coral") if recording else None)
        p.end()

    # ---- sources ----
    def reload_sources(self):
        def load():
            try:
                return backend.get().list_sources()
            except backend.BackendMissing:
                return []

        run_task(load, on_done=self._set_sources)

    def _set_sources(self, sources):
        self._sources = sources
        cfg, _ = settings.load()
        current = self.current_source_name() or cfg.source
        self.source.blockSignals(True)
        self.source.clear()
        if not sources:
            self.source.addItem("No inputs found")
            self.source.setEnabled(False)
            self.source.blockSignals(False)
            return
        self.source.setEnabled(self.session is None)
        last_kind = None
        for s in sources:
            if last_kind is not None and s.kind != last_kind:
                self.source.insertSeparator(self.source.count())
            last_kind = s.kind
            self.source.addItem(s.short_label, s.name)
            tip = s.label + (" (system default input)" if s.is_default and s.kind == INPUT else "")
            self.source.setItemData(self.source.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        idx = self.source.findData(current) if current else -1
        if idx < 0:
            d = backend.get().default_source(sources)
            idx = self.source.findData(d.name) if d else 0
            if current and self._sources_loaded is False and cfg.source:
                self.message.emit("The saved input is not available; using the default input.")
        self.source.setCurrentIndex(max(0, idx))
        self.source.blockSignals(False)
        self._sources_loaded = True
        self._restart_monitor()

    def current_source_name(self) -> str:
        return self.source.currentData() or ""

    def current_source(self) -> Source | None:
        name = self.current_source_name()
        return next((s for s in self._sources if s.name == name), None)

    def _source_chosen(self, _index):
        cfg, _ = settings.load()
        s = self.current_source()
        cfg.source = "" if (s is None or (s.is_default and s.kind == INPUT)) else s.name
        settings.save(cfg)
        self._restart_monitor()
        if self.listen.isChecked():
            self._listener.start(self.current_source())

    # ---- monitoring ----
    def set_window_shown(self, shown: bool):
        """The meter runs while the window is on screen, not minimized or hidden to the tray."""
        if shown == self._window_shown:
            return
        self._window_shown = shown
        if not shown:
            self._wave_timer.stop()
        self._restart_monitor()

    def _want_monitor(self) -> bool:
        return self.session is None and self._sources_loaded and (self._window_shown or self.listen.isChecked())

    def _restart_monitor(self):
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        if self._want_monitor():
            self._monitor = monitor.LevelMonitor(self.current_source())
            self._monitor.start()

    def _toggle_listen(self, on: bool):
        if on:
            self._listener.start(self.current_source())
            self.message.emit("Listening to the input. Use headphones to avoid feedback.")
        else:
            self._listener.stop()
        self._restart_monitor()

    # ---- recording ----
    def attach(self, sess: recorder.Session | None):
        was = self.session is not None
        self.session = sess
        if sess is None:
            self._close_note()
        if sess is not None and self._monitor:
            self._monitor.stop()
            self._monitor = None
        if sess is None and was:
            self._restart_monitor()
        self.source.setEnabled(sess is None and bool(self._sources))
        self._update_buttons()
        self.recording_changed.emit(sess is not None)

    def toggle_record(self):
        if self._busy:
            return
        if self.session is not None:
            self.stop()
        else:
            self.start()

    def start(self, quick_note: bool = False):
        cfg, _ = settings.load()
        s = self.current_source()
        source = "" if s is None or (s.is_default and s.kind == INPUT) else s.name
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        self._busy = True
        self._update_buttons()

        def go():
            return recorder.start(self.library, source=source, rate=cfg.sample_rate, channels=cfg.channels,
                                  quick_note=quick_note)

        def ok(sess):
            self._busy = False
            self.attach(sess)
            self.started.emit(sess.rec.id)

        def fail(msg):
            self._busy = False
            self._update_buttons()
            self._restart_monitor()
            self.message.emit(f"Could not start recording: {msg}")

        run_task(go, on_done=ok, on_error=fail)

    def stop(self):
        sess = self.session
        if sess is None:
            return
        try:
            sess.stop()
        except recorder.RecorderError as e:
            self.message.emit(str(e))
        rid = sess.rec.id
        self.attach(None)
        self.stopped.emit(rid)
        self.message.emit("Saving the recording…")

    def add_marker(self):
        """Mark the current moment of the recording, then offer a note field."""
        sess = self.session
        if sess is None:
            return
        try:
            sess.mark()
        except recorder.RecorderError as e:
            self.message.emit(str(e))
            return
        self.message.emit(f"Marker at {fmt_duration(sess.status().get('elapsed', 0))}.")
        self.note.clear()
        self.note.show()
        self.note.setFocus()
        self._note_timer.start()

    def _save_note(self):
        text = self.note.text().strip()
        if text and self.session is not None:
            try:
                self.session.note(text)
            except recorder.RecorderError as e:
                self.message.emit(str(e))
        self._close_note()

    def _close_note(self):
        self._note_timer.stop()
        if self.note.isVisible():
            self.note.hide()
            self.note.clear()
            self.window().setFocus()

    def toggle_pause(self):
        sess = self.session
        if sess is None:
            return
        try:
            if sess.status().get("state") == recorder.S_PAUSED:
                sess.resume()
            else:
                sess.pause()
        except recorder.RecorderError as e:
            self.message.emit(str(e))

    def _update_buttons(self):
        rec = self.session is not None
        t = theme.current()
        if rec:
            self.record_btn.setIcon(icon("stop", "coral_deep"))
            self.record_btn.setText("Stop")
            self.record_btn.setToolTip("Stop and save (Ctrl+R)")
            glow = theme.color("on_deep", 0.35)
        else:
            self.record_btn.setIcon(dot_icon(QColor("#ffffff"), 44, ring=False))
            self.record_btn.setText("Record")
            self.record_btn.setToolTip("Start recording (Ctrl+R)")
            glow = QColor(t.coral_deep)
            glow.setAlphaF(0.55)
        self._glow.setColor(glow)
        theme.set_role(self.record_btn, recording=rec)
        self.record_btn.setAccessibleName(self.record_btn.text())
        self.record_btn.setEnabled(not self._busy)
        self.pause_btn.setVisible(rec)
        self.pause_btn.setEnabled(rec and not self._busy)
        if not rec:
            self.elapsed.setText("0:00:00")
            self.state_label.setText("")
        self._wake_waves()

    # ---- ticking ----
    def _tick(self):
        sess = self.session
        if sess is not None:
            if not sess.rec.folder.exists() or not sess.alive():
                if sess.rec.folder.exists() and sess.rec.reload().meta.state == "recording" and sess.rec.takes_dir.exists():
                    # Supervisor died: the next library refresh triggers recovery.
                    self.message.emit("The recorder stopped unexpectedly; recovering the recording…")
                rid = sess.rec.id
                self.attach(None)
                self.stopped.emit(rid)
                return
            st = sess.status()
            self.elapsed.setText(fmt_duration(st.get("elapsed", 0), always_hours=True))
            paused = st.get("state") == recorder.S_PAUSED
            if st.get("state") != self._state:
                self._state = st.get("state") or ""
                self.state_label.setText("PAUSED" if paused else "● REC")
                self.state_label.setStyleSheet("" if paused else f"color: {theme.current().coral};")
                self.pause_btn.setIcon(icon("record") if paused else icon("pause", "on_deep"))
                self._wake_waves()
            self.pause_btn.setToolTip("Resume recording (Ctrl+Shift+R)" if paused else "Pause recording (Ctrl+Shift+R)")
            take = sess.current_take()
            db = None
            if take is not None and not paused:
                db, clip = levels.tail_peak(take, st.get("rate", 48000), st.get("channels", 1))
                self.meter.set_level(db, clip)
            else:
                self.meter.set_level(FLOOR_DB)
            self._show_warning(st.get("warning") or self._silence_hint(db))
        else:
            self._state = ""
            db = None
            if self._monitor and self._monitor.running():
                db = self._monitor.level
                self.meter.set_level(db, self._monitor.take_clip())
                if db > FLOOR_DB:
                    self._wake_waves()
            else:
                self.meter.set_level(FLOOR_DB)
            self._show_warning(self._silence_hint(db))

    def _silence_hint(self, db: float | None) -> str:
        """A hint once the input has been exactly silent for a while; None level = not measuring."""
        if db is None or db > SILENT_DB:
            self._silent_since = None
            return ""
        now = time.monotonic()
        if self._silent_since is None:
            self._silent_since = now
        secs = now - self._silent_since
        return SILENT_HINT.format(s=int(secs)) if secs >= SILENT_AFTER_S else ""

    def _show_warning(self, text: str):
        if text != self.warning.text():
            self.warning.setText(text)
        self.warning.setVisible(bool(text))

    def shutdown(self):
        self._timer.stop()
        if self._monitor:
            self._monitor.stop()
        self._listener.stop()


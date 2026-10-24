"""Recorder controls: source, level meter, listen, record / pause / stop, elapsed time."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPalette
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from .. import recorder, settings
from ..audio import levels, monitor, pipewire
from ..library import Library
from .common import RECORD_RED, dot_icon, fmt_duration, icon, run_task

log = logging.getLogger(__name__)

FLOOR_DB = -60.0
# Exact digital silence: a connected microphone with its gain up never produces it.
SILENT_DB = levels.SILENCE_DB + 1
SILENT_AFTER_S = 4.0
SILENT_HINT = ("No sound from this input for {s} seconds. Check that the microphone is connected, "
               "not muted and its gain is up, or pick another input.")


class LevelMeter(QWidget):
    """Horizontal peak meter with a decaying peak-hold mark and a clip lamp."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(10)
        self.setMaximumHeight(12)
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
        return QSize(200, 10)

    @staticmethod
    def _frac(db: float) -> float:
        return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        lamp = 10
        r = QRectF(0, 0, self.width() - lamp - 6, self.height())
        track = QColor(pal.color(QPalette.ColorRole.Text))
        track.setAlpha(28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 3, 3)
        w = r.width() * self._frac(self._level)
        green, amber = QColor("#30a46c"), QColor("#f5a524")
        p.setBrush(green if self._level < -12 else amber if self._level < -3 else RECORD_RED)
        if w > 0:
            p.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), 3, 3)
        hx = r.left() + r.width() * self._frac(self._hold)
        if self._hold > FLOOR_DB + 1:
            p.setBrush(pal.color(QPalette.ColorRole.Text))
            p.drawRect(QRectF(hx - 1, r.top(), 2, r.height()))
        clipping = time.monotonic() < self._clip_until
        lamp_color = RECORD_RED if clipping else track
        p.setBrush(lamp_color)
        p.drawEllipse(QRectF(self.width() - lamp, (self.height() - lamp) / 2, lamp, lamp))


class SourceCombo(QComboBox):
    aboutToShow = Signal()

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
        self._sources: list[pipewire.Source] = []
        self._monitor: monitor.LevelMonitor | None = None
        self._listener = monitor.Listener()
        self._busy = False
        self._window_shown = True
        self._silent_since: float | None = None
        self._build()
        self._timer = QTimer(self, interval=100, timeout=self._tick)
        self._timer.start()
        self._sources_loaded = False
        self.reload_sources()

    # ---- layout ----
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 6)
        lay.setSpacing(8)
        row = QHBoxLayout()
        self.source = SourceCombo()
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source.setMinimumContentsLength(12)
        self.source.setToolTip("Input to record from")
        self.source.setAccessibleName("Input source")
        self.source.aboutToShow.connect(self.reload_sources)
        self.source.activated.connect(self._source_chosen)
        row.addWidget(self.source, 1)
        self.listen = QToolButton()
        self.listen.setIcon(icon("listen"))
        self.listen.setCheckable(True)
        self.listen.setToolTip("Listen to this input through your speakers or headphones")
        self.listen.setAccessibleName("Listen to input")
        self.listen.toggled.connect(self._toggle_listen)
        row.addWidget(self.listen)
        lay.addLayout(row)

        self.meter = LevelMeter()
        lay.addWidget(self.meter)

        ctl = QHBoxLayout()
        ctl.setSpacing(6)
        self.record_btn = QToolButton()
        self.record_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.record_btn.setIconSize(QSize(22, 22))
        self.record_btn.setMinimumHeight(36)
        self.record_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.record_btn.clicked.connect(self.toggle_record)
        ctl.addWidget(self.record_btn, 1)
        self.pause_btn = QToolButton()
        self.pause_btn.setIcon(icon("pause"))
        self.pause_btn.setIconSize(QSize(20, 20))
        self.pause_btn.setMinimumSize(36, 36)
        self.pause_btn.setToolTip("Pause recording (Ctrl+Shift+R)")
        self.pause_btn.setAccessibleName("Pause recording")
        self.pause_btn.clicked.connect(self.toggle_pause)
        ctl.addWidget(self.pause_btn)
        lay.addLayout(ctl)

        info = QHBoxLayout()
        self.elapsed = QLabel("0:00:00")
        f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        f.setPointSizeF(max(13.0, self.font().pointSizeF() * 1.45))
        self.elapsed.setFont(f)
        self.elapsed.setAccessibleName("Recorded time")
        info.addWidget(self.elapsed)
        info.addStretch(1)
        self.state_label = QLabel("")
        info.addWidget(self.state_label)
        lay.addLayout(info)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #d9822b;")
        self.warning.hide()
        lay.addWidget(self.warning)
        self._update_buttons()

    # ---- sources ----
    def reload_sources(self):
        def load():
            return pipewire.list_sources()

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
            self.source.addItem(s.label, s.name)
            tip = s.label + (" (system default input)" if s.is_default and s.kind == pipewire.INPUT else "")
            self.source.setItemData(self.source.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        idx = self.source.findData(current) if current else -1
        if idx < 0:
            d = pipewire.default_source(sources)
            idx = self.source.findData(d.name) if d else 0
            if current and self._sources_loaded is False and cfg.source:
                self.message.emit("The saved input is not available; using the default input.")
        self.source.setCurrentIndex(max(0, idx))
        self.source.blockSignals(False)
        self._sources_loaded = True
        self._restart_monitor()

    def current_source_name(self) -> str:
        return self.source.currentData() or ""

    def current_source(self) -> pipewire.Source | None:
        name = self.current_source_name()
        return next((s for s in self._sources if s.name == name), None)

    def _source_chosen(self, _index):
        cfg, _ = settings.load()
        s = self.current_source()
        cfg.source = "" if (s is None or (s.is_default and s.kind == pipewire.INPUT)) else s.name
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

    def start(self):
        cfg, _ = settings.load()
        s = self.current_source()
        source = "" if s is None or (s.is_default and s.kind == pipewire.INPUT) else s.name
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        self._busy = True
        self._update_buttons()

        def go():
            return recorder.start(self.library, source=source, rate=cfg.sample_rate, channels=cfg.channels)

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
        if rec:
            self.record_btn.setIcon(icon("stop"))
            self.record_btn.setText("Stop")
            self.record_btn.setToolTip("Stop and save (Ctrl+R)")
        else:
            self.record_btn.setIcon(dot_icon(RECORD_RED, 44))
            self.record_btn.setText("Record")
            self.record_btn.setToolTip("Start recording (Ctrl+R)")
        self.record_btn.setAccessibleName(self.record_btn.text())
        self.record_btn.setEnabled(not self._busy)
        self.pause_btn.setVisible(rec)
        self.pause_btn.setEnabled(rec and not self._busy)
        if not rec:
            self.elapsed.setText("0:00:00")

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
            self.state_label.setText("Paused" if paused else "● Recording")
            self.state_label.setStyleSheet("" if paused else f"color: {RECORD_RED.name()}; font-weight: 600;")
            self.pause_btn.setIcon(icon("record" if paused else "pause"))
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
            self.state_label.setText("")
            db = None
            if self._monitor and self._monitor.running():
                db = self._monitor.level
                self.meter.set_level(db, self._monitor.take_clip())
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


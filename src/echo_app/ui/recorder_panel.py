"""Recorder controls: source, level meter, listen, computer audio, record / pause / stop, elapsed time."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
                               QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)

from .. import recorder, settings
from ..audio import backend, levels, monitor
from ..audio.backend import DEFAULT_OUTPUT, INPUT, Source
from ..library import Library
from . import motion, theme
from .common import Wordmark, dot_icon, fmt_duration, icon, run_task
from .inputs import FLOOR_DB, InputPanel, LevelMeter, SourceCombo

log = logging.getLogger(__name__)
WAVE_HEIGHT = 64
# Exact digital silence: a connected microphone with its gain up never produces it.
SILENT_DB = levels.SILENCE_DB + 1
SILENT_AFTER_S = 4.0
NOTE_IDLE_MS = 10_000  # the marker note field closes after this long without typing
GAIN_MAX_PCT = 150  # pipewire.GAIN_MAX
SILENT_HINT = ("No sound from this input for {s} seconds. Check that the microphone is connected, "
               "not muted and its gain is up, or pick another input.")
# In the sidebar the hint is a word on the empty meter: a noise gate makes exact silence between
# sentences all the time, and a line of text coming and going there moved the controls under it.
SILENT_NOTE = "No sound for {s} s"


class RecorderPanel(QWidget):
    started = Signal(str)  # recording id
    stopped = Signal(str)
    message = Signal(str)  # transient status-bar message
    recording_changed = Signal(bool)

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self.session: recorder.Session | None = None
        self.marks = 0  # markers taken in the current recording
        self._sources: list[Source] = []
        self._monitor: monitor.LevelMonitor | None = None
        self._out_monitor: monitor.LevelMonitor | None = None  # the computer audio, when it is recorded too
        self._listener = monitor.Listener()
        self._busy = False
        self._window_shown = True
        self._silent_since: float | None = None
        self.silence = ""  # the silent-input hint, shown in full on the welcome screen
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
        brand.setSpacing(2)
        self.wordmark = Wordmark(2.1)
        brand.addWidget(self.wordmark)
        brand.addStretch(1)
        self.corner = brand  # the window adds its People and menu buttons here
        lay.addLayout(brand)

        # At rest the block is only the Record button; while recording it is a coral card with the
        # state, the time, the level and Pause, Stop and Marker.
        self.block = QFrame()
        self.block.setObjectName("recblock")
        bl = QVBoxLayout(self.block)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        state_row = QHBoxLayout()
        state_row.setSpacing(4)
        self.pulse = motion.PulseDot("coral")
        state_row.addWidget(self.pulse)
        self.state_label = QLabel("")
        self.state_label.setFont(theme.display_font(0.82, QFont.Weight.ExtraBold))
        state_row.addWidget(self.state_label, 1)
        bl.addLayout(state_row)
        self.elapsed = QLabel("0:00:00")
        self.elapsed.setFont(theme.display_font(2.5, QFont.Weight.Light, tabular=True))
        self.elapsed.setAccessibleName("Recorded time")
        bl.addWidget(self.elapsed)
        self.meter = LevelMeter()
        bl.addWidget(self.meter)
        self.call_meter = LevelMeter()  # the computer audio while a call is recorded
        self.call_meter.setToolTip("Computer audio level: what the default output is playing.")
        self.call_meter.setAccessibleName("Computer audio level")
        bl.addWidget(self.call_meter)

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
        self.pause_btn = QToolButton()
        self.pause_btn.setObjectName("pause")
        self.pause_btn.setIcon(icon("pause", "on_deep"))
        self.pause_btn.setIconSize(QSize(18, 18))
        self.pause_btn.setFixedSize(46, 46)
        self.pause_btn.setToolTip("Pause recording (Ctrl+Shift+R)")
        self.pause_btn.setAccessibleName("Pause recording")
        self.pause_btn.clicked.connect(self.toggle_pause)
        ctl.addWidget(self.pause_btn)
        ctl.addWidget(self.record_btn, 1)
        self.mark_btn = QToolButton()
        self.mark_btn.setObjectName("pause")
        self.mark_btn.setIcon(icon("bookmark", "on_deep"))
        self.mark_btn.setIconSize(QSize(18, 18))
        self.mark_btn.setFixedSize(46, 46)
        self.mark_btn.setToolTip("Add a marker (M)")
        self.mark_btn.setAccessibleName("Add marker")
        self.mark_btn.clicked.connect(self.add_marker)
        ctl.addWidget(self.mark_btn)
        self._ripple = motion.Ripple(self.mark_btn, "coral")
        bl.addLayout(ctl)

        self.warning = QLabel("")
        self.warning.setWordWrap(True)
        theme.set_role(self.warning, warn=True)
        self.warning.hide()
        bl.addWidget(self.warning)

        # After a marker: an optional note, typed without stopping the recording.
        self.note = QLineEdit()
        self.note.setObjectName("markernote")
        self.note.setPlaceholderText("Note for this marker (Enter to save, Esc to skip)")
        self.note.setAccessibleName("Marker note")
        self.note.addAction(icon("bookmark", "on_deep"), QLineEdit.ActionPosition.LeadingPosition)
        self.note.returnPressed.connect(self._save_note)
        self.note.textEdited.connect(lambda _t: self._note_timer.start())
        self.note.hide()
        bl.addWidget(self.note)
        self._note_timer = QTimer(self, singleShot=True, interval=NOTE_IDLE_MS, timeout=self._close_note)
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.note, activated=self._close_note,
                        context=Qt.ShortcutContext.WidgetShortcut)
        self._note_esc = esc
        lay.addWidget(self.block)

        # The input, named under Record; a click opens everything about it.
        self.source_btn = QToolButton()
        self.source_btn.setObjectName("sourcebtn")
        self.source_btn.setIcon(icon("mic", "on_deep_muted"))
        self.source_btn.setIconSize(QSize(14, 14))
        self.source_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source_btn.setToolTip("Input, level, gain and computer audio")
        self.source_btn.setAccessibleName("Input settings")
        self.source_btn.clicked.connect(self.show_inputs)
        lay.addWidget(self.source_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        self.input_panel = InputPanel(self)
        il = self.input_panel.body
        head = QLabel("INPUT")
        head.setFont(theme.display_font(0.78, QFont.Weight.ExtraBold))
        theme.set_role(head, eyebrow=True)
        il.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.source = SourceCombo()
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source.setMinimumContentsLength(14)
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
        il.addLayout(row)
        self.input_meter = LevelMeter()
        il.addWidget(self.input_meter)

        # The input's gain: the device's own volume, so it works while recording and the meter
        # above shows the effect at once. Hidden where the backend cannot set it.
        self.gain_row = QWidget()
        gl = QHBoxLayout(self.gain_row)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        mic = QLabel()
        mic.setPixmap(icon("mic", "on_deep_muted").pixmap(16, 16))
        gl.addWidget(mic)
        self.gain = QSlider(Qt.Orientation.Horizontal)
        self.gain.setRange(0, GAIN_MAX_PCT)
        self.gain.setSingleStep(1)
        self.gain.setPageStep(10)
        self.gain.setToolTip("Input gain: the microphone's volume in the system, the same setting as the "
                             "desktop's sound settings. Above 100% boosts it in software. Double-click for 100%.")
        self.gain.setAccessibleName("Input gain")
        self.gain.valueChanged.connect(self._gain_moved)
        self.gain.installEventFilter(self)
        gl.addWidget(self.gain, 1)
        self.gain_label = QLabel("100%")
        self.gain_label.setFont(theme.display_font(0.85, QFont.Weight.Bold, tabular=True))
        self.gain_label.setMinimumWidth(self.gain_label.fontMetrics().horizontalAdvance("150%") + 2)
        self.gain_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        gl.addWidget(self.gain_label)
        self.gain_row.hide()
        il.addWidget(self.gain_row)
        self._gain_timer = QTimer(self, singleShot=True, interval=60, timeout=self._apply_gain)

        # A call: what the computer plays, recorded as a second track next to the microphone.
        self.computer_row = QWidget()
        cl = QVBoxLayout(self.computer_row)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.setSpacing(8)
        self.computer = QToolButton()
        self.computer.setCheckable(True)
        self.computer.setIcon(icon("volume", "on_deep"))
        self.computer.setIconSize(QSize(16, 16))
        self.computer.setText("Also record computer audio")
        self.computer.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.computer.setToolTip("Also record what the computer plays, such as the other side of a call, as a "
                                 "second track. The call app keeps its microphone and sound. Use headphones.")
        self.computer.setAccessibleName("Also record computer audio")
        self.computer.setChecked(settings.load()[0].computer_audio)
        self.computer.toggled.connect(self._toggle_computer)
        cl.addWidget(self.computer, 0, Qt.AlignmentFlag.AlignLeft)
        self.out_meter = LevelMeter()
        self.out_meter.setToolTip("Computer audio level: what the default output is playing.")
        self.out_meter.setAccessibleName("Computer audio level")
        self.out_meter.setVisible(self.computer.isChecked())
        cl.addWidget(self.out_meter)
        self.computer_row.hide()
        il.addWidget(self.computer_row)
        self._update_buttons()

    def add_corner(self, widget: QWidget):
        """A button in the top row, beside the wordmark."""
        self.corner.addWidget(widget)

    def show_inputs(self):
        """The input panel, under the input's name."""
        self.reload_sources()
        self.input_panel.setFixedWidth(max(280, self.width() - 16))
        self.input_panel.adjustSize()
        at = self.source_btn.mapToGlobal(self.source_btn.rect().bottomLeft())
        left = self.mapToGlobal(self.rect().topLeft()).x() + 8
        self.input_panel.move(left, at.y() + 6)
        self.input_panel.show()

    def _update_source_btn(self):
        s = self.current_source()
        name = s.short_label if s is not None else (self.source.currentText() or "No input")
        if self.computer_audio_on():
            name += " + computer audio"
        silent = self.meter._note
        self.source_btn.setText(f"{name} · {silent.lower()}" if silent else name)
        theme.set_role(self.source_btn, warn=bool(silent))
        self.source_btn.setIcon(icon("mic", "amber" if silent else "on_deep_muted"))

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
            self._update_source_btn()
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
        self._show_computer_row()
        self._restart_monitor()
        self._load_gain()
        self._update_source_btn()

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
        self._show_computer_row()
        self._restart_monitor()
        self._load_gain()
        if self.listen.isChecked():
            self._listener.start(self.current_source())
        self._update_source_btn()

    # ---- computer audio ----
    def _show_computer_row(self):
        """Offered for an input on a backend that records outputs; a monitor is already the computer audio."""
        try:
            records = backend.get().records_outputs
        except backend.BackendMissing:
            records = False
        s = self.current_source()
        self.computer_row.setVisible(records and (s is None or s.kind == INPUT))

    def computer_audio_on(self) -> bool:
        return self.computer.isChecked() and not self.computer_row.isHidden()

    def _toggle_computer(self, on: bool):
        cfg, _ = settings.load()
        cfg.computer_audio = on
        settings.save(cfg)
        self.out_meter.setVisible(on)
        self._restart_monitor()
        self._update_source_btn()

    # ---- gain ----
    def _load_gain(self):
        src = self.current_source()

        def load():
            try:
                return src, backend.get().gain(src)
            except backend.BackendMissing:
                return src, None

        run_task(load, on_done=self._show_gain)

    def _show_gain(self, result):
        src, value = result
        if src is not self.current_source() or self._gain_timer.isActive():
            return  # the source changed meanwhile, or the user is moving the slider
        self.gain_row.setVisible(value is not None)
        if value is not None:
            self.gain.blockSignals(True)
            self.gain.setValue(round(value * 100))
            self.gain.blockSignals(False)
            self.gain_label.setText(f"{self.gain.value()}%")

    def _gain_moved(self, pct: int):
        self.gain_label.setText(f"{pct}%")
        self._gain_timer.start()

    def _apply_gain(self):
        try:
            ok = backend.get().set_gain(self.current_source(), self.gain.value() / 100)
        except backend.BackendMissing:
            ok = False
        if not ok:
            self.message.emit("Could not change the input gain.")
            self._load_gain()

    def eventFilter(self, obj, event):
        if obj is self.gain and event.type() == QEvent.Type.MouseButtonDblClick:
            self.gain.setValue(100)
            return True
        return super().eventFilter(obj, event)

    # ---- monitoring ----
    def set_window_shown(self, shown: bool):
        """The meter runs while the window is on screen, not minimized or hidden to the tray."""
        if shown == self._window_shown:
            return
        self._window_shown = shown
        if not shown:
            self._wave_timer.stop()
        else:
            self._load_gain()  # it may have been changed in the desktop's settings meanwhile
        self._restart_monitor()

    def _want_monitor(self) -> bool:
        return self.session is None and self._sources_loaded and (self._window_shown or self.listen.isChecked())

    def _restart_monitor(self):
        for m in (self._monitor, self._out_monitor):
            if m:
                m.stop()
        self._monitor = self._out_monitor = None
        if self._want_monitor():
            self._monitor = monitor.LevelMonitor(self.current_source())
            self._monitor.start()
            if self.computer_audio_on():
                self._out_monitor = monitor.LevelMonitor(DEFAULT_OUTPUT)
                self._out_monitor.start()

    def _stop_monitors(self):
        for m in (self._monitor, self._out_monitor):
            if m:
                m.stop()
        self._monitor = self._out_monitor = None

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
        if sess is not None and (self.session is None or self.session.rec.id != sess.rec.id):
            self.marks = len(sess.rec.meta.markers)  # a recording attached midway may have some
        self.session = sess
        if sess is None:
            self._close_note()
        if sess is not None:
            self._stop_monitors()
        if sess is None and was:
            self._restart_monitor()
        self.source.setEnabled(sess is None and bool(self._sources))
        self.computer.setEnabled(sess is None)
        # A recording started elsewhere (the CLI, a shortcut) shows what it records.
        two = sess is not None and bool((recorder.load_session(sess.rec) or {}).get("computer_audio"))
        self.out_meter.setVisible(two if sess is not None else self.computer.isChecked())
        self._two_tracks = two
        if sess is not None:
            self.input_panel.hide()
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
        computer_audio = self.computer_audio_on() and not quick_note  # a quick note is the user alone
        self._stop_monitors()
        self._busy = True
        self._update_buttons()

        def go():
            return recorder.start(self.library, source=source, rate=cfg.sample_rate, channels=cfg.channels,
                                  quick_note=quick_note, computer_audio=computer_audio)

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
        self.marks += 1
        self._ripple.play()
        self.message.emit(f"Marker at {fmt_duration(sess.status().get('elapsed', 0))}.")
        self.note.clear()
        self.note.show()
        self.note.setFocus()
        self._note_timer.start()

    def mark_quietly(self) -> bool:
        """A marker with no note field: from the tray or the dock, where the window may be hidden."""
        sess = self.session
        if sess is None:
            return False
        try:
            sess.mark()
        except recorder.RecorderError as e:
            self.message.emit(str(e))
            return False
        self.marks += 1
        self._ripple.play()
        return True

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
        was = bool(self.block.property("recording") == "true")
        theme.set_role(self.block, recording=rec)
        if rec != was:
            motion.fade(self.block, 1.0, motion.MEDIUM, start=0.0)  # the block changes, it does not jump
        self.block.layout().setContentsMargins(*((16, 14, 16, 16) if rec else (0, 0, 0, 0)))
        for w in (self.pulse, self.state_label, self.elapsed, self.meter, self.mark_btn):
            w.setVisible(rec)
        self.call_meter.setVisible(rec and getattr(self, "_two_tracks", False))
        self.source_btn.setVisible(not rec)
        self.mark_btn.setEnabled(rec and not self._busy)
        if rec:
            self.record_btn.setIcon(icon("stop", "deep_top"))
            self.record_btn.setText("Stop")
            self.record_btn.setToolTip("Stop and save (Ctrl+R)")
            glow = QColor(t.coral_deep)
            glow.setAlphaF(0.3)
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
                self.state_label.setText("PAUSED" if paused else "RECORDING")
                tone = theme.current().amber if paused else "#ffb4b4"
                self.state_label.setStyleSheet(f"color: {tone}; letter-spacing: 1px;")
                self.pulse.set_paused(paused)
                motion.fade(self.elapsed, 0.55 if paused else 1.0, motion.MEDIUM)
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
            out = st.get("out_take")
            if out and not paused:
                self.out_meter.set_level(*levels.tail_peak(sess.rec.takes_dir / out, st.get("rate", 48000), 1))
            else:
                self.out_meter.set_level(FLOOR_DB)
            self.call_meter.set_level(self.out_meter._level)
            self._show_warning(st.get("warning") or "")
            self._show_silence(self._silence_hint(db))
        else:
            self._state = ""
            db = None
            if self._monitor and self._monitor.running():
                db = self._monitor.level
                clip = self._monitor.take_clip()
                self.meter.set_level(db, clip)
                self.input_meter.set_level(db, clip)
                if db > FLOOR_DB:
                    self._wake_waves()
            else:
                self.meter.set_level(FLOOR_DB)
                self.input_meter.set_level(FLOOR_DB)
            if self._out_monitor and self._out_monitor.running():
                self.out_meter.set_level(self._out_monitor.level, self._out_monitor.take_clip())
            else:
                self.out_meter.set_level(FLOOR_DB)
            self._show_warning("")
            self._show_silence(self._silence_hint(db))

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

    def _show_silence(self, hint: str):
        self.silence = hint
        secs = int(time.monotonic() - self._silent_since) if hint and self._silent_since is not None else 0
        note = SILENT_NOTE.format(s=secs) if hint else ""
        changed = note != self.meter._note
        self.meter.set_note(note, hint)
        self.input_meter.set_note(note, hint)
        if changed:
            self._update_source_btn()

    def _show_warning(self, text: str):
        if text != self.warning.text():
            self.warning.setText(text)
        self.warning.setVisible(bool(text))

    def shutdown(self):
        self._timer.stop()
        self._stop_monitors()
        self._listener.stop()


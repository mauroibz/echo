"""The recording dock: a small pill above other windows, for recording without the window."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from .. import recorder
from ..library import Library
from . import motion, theme
from .common import dot_icon, fmt_duration, icon
from .library_view import status_of

MINIMAL_AFTER_S = 5.0  # while recording, without the pointer over it, the dock shrinks to the time
SAVED_FOR_S = 10.0  # "Saved" stays this long unless Open or Done is pressed
FLOOR_DB = -60.0


class LevelWave(QWidget):
    """A small wave that rises with the input's level and travels while recording."""

    def __init__(self, level, parent=None):
        super().__init__(parent)
        self.level = level  # () -> dB
        self.live = False
        self._t = 0.0
        self.setFixedSize(QSize(96, 26))
        motion.clock().tick.connect(self._on_tick)
        key = id(self)
        self.destroyed.connect(lambda _o=None: motion.clock().release_key(key))

    def set_live(self, live: bool) -> None:
        self.live = live
        if live and self.isVisible():
            motion.clock().hold(self)
        else:
            motion.clock().release(self)
        self.update()

    def showEvent(self, e):
        if self.live:
            motion.clock().hold(self)
        super().showEvent(e)

    def hideEvent(self, e):
        motion.clock().release(self)
        super().hideEvent(e)

    def _on_tick(self, t: float):
        if self.isVisible():
            self._t = t
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        frac = max(0.0, min(1.0, (self.level() - FLOOR_DB) / -FLOOR_DB)) if self.live else 0.0
        amp = (2 + 9 * frac) if self.live else 1.0
        color = theme.color("coral", 1.0 if self.live else 0.35)
        for k, (alpha, speed, wl) in enumerate(((1.0, 3.2, 30.0), (0.4, -2.1, 44.0))):
            path = QPainterPath(QPointF(0, h / 2))
            x = 0.0
            while x <= w:
                y = h / 2 + amp * math.sin(2 * math.pi * x / wl + self._t * speed + k) * math.sin(math.pi * x / w)
                path.lineTo(x, y)
                x += 2
            c = QColor(color)
            c.setAlphaF(c.alphaF() * alpha)
            p.setPen(QPen(c, 2.2 if k == 0 else 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
        p.end()


class RecordDock(QWidget):
    """Record, pause, mark and stop from a pill that stays above other windows. All recording
    goes through the recorder panel; the dock only shows its state and forwards the buttons."""

    open_window = Signal(str)  # the recording to select, or "" for none
    visibility_changed = Signal(bool)

    def __init__(self, panel, library: Library):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.panel = panel
        self.library = library
        self.setObjectName("sidebar")  # styled like the sidebar it comes from
        self.setWindowTitle("Echo recording")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("Echo recording dock")
        self.state = "rest"  # rest | recording | saved
        self.minimal = False
        self.saved_id = ""
        self._saved_at = 0.0
        self._hover_left = time.monotonic()
        self._hovered = False
        self._last_session = None
        self._build()
        self._timer = QTimer(self, interval=200, timeout=self.refresh)
        # The window's shortcuts do not reach a hidden window: the dock has its own.
        for keys, fn in (("Ctrl+R", self._record), ("Ctrl+Shift+R", self.panel.toggle_pause), ("M", self._mark),
                         ("Ctrl+Shift+D", lambda: self.open_window.emit(""))):
            QShortcut(QKeySequence(keys), self, activated=fn)

    # ---- layout ----
    def _button(self, ic: str, tip: str, role: str = "on_deep", size: int = 40, name: str = "dockbtn") -> QToolButton:
        b = QToolButton()
        b.setObjectName(name)
        b.setIcon(icon(ic, role))
        b.setIconSize(QSize(16, 16))
        b.setFixedSize(size, size)
        b.setToolTip(tip)
        b.setAccessibleName(tip.split(" (")[0])
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 10, 10)
        lay.setSpacing(12)
        self.word = QLabel("echo")
        self.word.setFont(theme.display_font(1.25, QFont.Weight.ExtraBold))
        lay.addWidget(self.word)
        self.pulse = motion.PulseDot("coral")
        lay.addWidget(self.pulse)
        self.time = QLabel("0:00")
        self.time.setFont(theme.display_font(1.55, QFont.Weight.Normal, tabular=True))
        self.time.setMinimumWidth(self.time.fontMetrics().horizontalAdvance("0:00:00") + 2)
        lay.addWidget(self.time)
        self.wave = LevelWave(lambda: self.panel.meter._level)
        lay.addWidget(self.wave)
        self.mic = QLabel()
        self.mic.setPixmap(icon("mic", "on_deep_muted").pixmap(14, 14))
        self.computer = QLabel()
        self.computer.setPixmap(icon("volume", "on_deep_muted").pixmap(14, 14))
        lay.addWidget(self.mic)
        lay.addWidget(self.computer)
        self.input_name = QLabel("")
        theme.set_role(self.input_name, dim=True)
        lay.addWidget(self.input_name)

        # After Stop, or a problem: a line of text (with progress under it while transcribing).
        self.info = QWidget()
        il = QVBoxLayout(self.info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(2)
        self.message = QLabel("")
        self.message.setFont(theme.display_font(0.95, QFont.Weight.Bold))
        il.addWidget(self.message)
        self.detail = QLabel("")
        self.detail.setFont(theme.display_font(0.82, QFont.Weight.DemiBold))
        self.detail.setStyleSheet(f"color: {theme.current().foam};")
        il.addWidget(self.detail)
        self.info.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.info)

        self.mark = self._button("bookmark", "Add a marker (M)")
        self.mark.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.mark.clicked.connect(self._mark)
        self._ripple = motion.Ripple(self.mark, "coral")
        lay.addWidget(self.mark)
        self.pause = self._button("pause", "Pause (Ctrl+Shift+R)")
        self.pause.clicked.connect(self.panel.toggle_pause)
        lay.addWidget(self.pause)
        self.record = self._button("record", "Record (Ctrl+R)", size=44, name="dockrecord")
        self.record.clicked.connect(self._record)
        lay.addWidget(self.record)
        self.open_btn = QToolButton()
        self.open_btn.setObjectName("dockbtn")
        self.open_btn.setFixedHeight(40)  # the pill's radius needs the full height
        self.open_btn.setText("Open")
        self.open_btn.clicked.connect(lambda: self.open_window.emit(self.saved_id))
        lay.addWidget(self.open_btn)
        self.done_btn = QToolButton()
        self.done_btn.setObjectName("flat")
        self.done_btn.setText("Done")
        self.done_btn.clicked.connect(self._done)
        lay.addWidget(self.done_btn)
        self.window_btn = self._button("details", "Back to the window (Ctrl+Shift+D)", "on_deep_muted", 36, "flat")
        self.window_btn.setIcon(icon("expand", "on_deep_muted"))
        self.window_btn.clicked.connect(lambda: self.open_window.emit(""))
        lay.addWidget(self.window_btn)

    # ---- state ----
    def showEvent(self, e):
        self._timer.start()
        self.refresh()
        super().showEvent(e)
        self.visibility_changed.emit(True)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)
        self.visibility_changed.emit(False)

    def refresh(self):
        sess = self.panel.session
        if sess is not None:
            self.state = "recording"
            self._last_session = sess.rec.id
        elif self.state == "recording":
            self.state, self.saved_id, self._saved_at = "saved", self._last_session or "", time.monotonic()
        if self.state == "saved" and time.monotonic() - self._saved_at > SAVED_FOR_S:
            self.state = "rest"
        status = sess.status() if sess is not None else {}
        paused = status.get("state") == recorder.S_PAUSED
        problem = (status.get("warning") or self.panel.silence) if sess is not None else ""
        if problem and "seconds" in problem:
            problem = self.panel.meter._note or problem  # the short form: "No sound for 12 s"
        away = not self._hovered and time.monotonic() - self._hover_left > MINIMAL_AFTER_S
        self.minimal = self.state == "recording" and away and not problem
        self._show(paused, problem)
        if sess is not None:
            self.time.setText(fmt_duration(status.get("elapsed", 0)))
            two = bool((recorder.load_session(sess.rec) or {}).get("computer_audio"))
            self.computer.setVisible(two and not self.minimal)
        elif self.state == "saved":
            self._show_saved()
        self.adjustSize()

    def _show(self, paused: bool, problem: str):
        rec, saved, rest, mini = (self.state == "recording", self.state == "saved", self.state == "rest",
                                  self.minimal)
        self.word.setVisible(rest)
        self.input_name.setVisible(rest)
        if rest:
            s = self.panel.current_source()
            self.input_name.setText(s.short_label if s is not None else "")
        self.pulse.setVisible(rec)
        self.pulse.set_paused(paused)
        self.time.setVisible(rec)
        self.time.setStyleSheet(f"color: {theme.current().amber};" if paused else "")
        full = rec and not mini
        self.wave.setVisible(full)
        self.wave.set_live(rec and not paused)
        self.mic.setVisible(full)
        if not rec:
            self.computer.setVisible(False)
        for w in (self.mark, self.pause):
            w.setVisible(full)
        self.record.setVisible(rest or full)
        self.record.setIcon(icon("stop", "deep_top") if rec else dot_icon(QColor("#ffffff"), 32))
        self.record.setToolTip("Stop and save (Ctrl+R)" if rec else "Record (Ctrl+R)")
        self.record.setAccessibleName("Stop" if rec else "Record")
        theme.set_role(self.record, recording=rec)
        self.pause.setIcon(icon("play" if paused else "pause", "on_deep"))
        self.pause.setToolTip("Resume (Ctrl+Shift+R)" if paused else "Pause (Ctrl+Shift+R)")
        n = self.panel.marks
        self.mark.setText(str(n) if n else "")
        self.mark.setFixedWidth(40 if not n else 40 + self.mark.fontMetrics().horizontalAdvance(str(n)) + 8)
        self.info.setVisible(saved or (rec and bool(problem)))
        if rec and problem:
            self.message.setText(problem)
            self.message.setStyleSheet(f"color: {theme.current().amber};")
            self.detail.hide()
        self.open_btn.setVisible(saved)
        self.done_btn.setVisible(saved)
        self.window_btn.setVisible(not saved and not mini)

    def _show_saved(self):
        rec = self.library.get(self.saved_id) if self.saved_id else None
        self.message.setStyleSheet("")
        length = f" · {fmt_duration(rec.meta.duration)}" if rec is not None and rec.meta.duration else ""
        self.message.setText(f"Saved{length}")
        st = status_of(rec) if rec is not None else None
        busy = st is not None and st.text and st.kind in ("busy", "wait")
        self.detail.setVisible(bool(busy))
        if busy:
            self.detail.setText(st.text)

    # ---- actions ----
    def _record(self):
        if self.panel.session is not None:
            self.panel.stop()
        else:
            self.state = "rest"
            self.panel.start()
        self._hover_left = time.monotonic()
        QTimer.singleShot(300, self.refresh)

    def _mark(self):
        if self.panel.mark_quietly():
            self._ripple.play()
            self.refresh()

    def _done(self):
        self.state = "rest"
        self.refresh()

    # ---- pointer ----
    def enterEvent(self, e):
        self._hovered = True
        if self.minimal:
            self.refresh()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._hover_left = time.monotonic()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.windowHandle() is not None:
            self.windowHandle().startSystemMove()  # works on Wayland too, where a window cannot move itself
            e.accept()
            return
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(theme.color("on_deep", 0.14), 1))
        g = theme.deep_gradient(r)
        g.setFinalStop(r.topRight())  # across the pill, not down it
        p.setBrush(g)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.end()

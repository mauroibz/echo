"""Motion: short animations where something changes, and whether to show them at all.

Every helper jumps to its end state when motion is off (the user's setting, the desktop's, or
`ECHO_REDUCE_MOTION=1`), so what the window shows afterwards is the same either way.
"""

from __future__ import annotations

import configparser
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QSizePolicy, QWidget

from .. import settings
from . import theme

FAST, MEDIUM, SLOW = 120, 240, 320  # ms: an icon, a panel, a row

_desktop: list[bool] = []  # whether the desktop has animations on, asked once


def desktop_animates() -> bool:
    """False when GNOME's "Animations" are off or KDE's animation speed is instant."""
    if not _desktop:
        _desktop.append(_ask_desktop())
    return _desktop[0]


def _ask_desktop() -> bool:
    kde = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kdeglobals"
    if kde.exists():
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cfg.read(kde, encoding="utf-8")
            factor = cfg.get("KDE", "AnimationDurationFactor", fallback=None)
            if factor is not None and float(factor) == 0:
                return False
        except (configparser.Error, ValueError, OSError):
            pass
    if shutil.which("gsettings") and "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        try:
            out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
                                 capture_output=True, text=True, timeout=1).stdout.strip()
            if out == "false":
                return False
        except (OSError, subprocess.SubprocessError):
            pass
    return True


def enabled() -> bool:
    if os.environ.get("ECHO_REDUCE_MOTION") == "1":
        return False
    return not settings.load()[0].reduce_motion and desktop_animates()


def _cache_enabled():
    """Settings are read from disk; within one event-loop pass the answer cannot change."""
    now = time.monotonic()
    if now - _cache_enabled.t > 0.5:
        _cache_enabled.v, _cache_enabled.t = enabled(), now
    return _cache_enabled.v


_cache_enabled.t, _cache_enabled.v = -1.0, True


def on() -> bool:
    if os.environ.get("ECHO_REDUCE_MOTION") == "1":
        return False  # checked first, so a test that turns motion on or off is obeyed at once
    return _cache_enabled()


def refresh() -> None:
    """After the setting changed: ask again on the next animation."""
    _cache_enabled.t = -1.0


def _run(anim: QPropertyAnimation, ms: int, curve=QEasingCurve.Type.OutCubic, done=None):
    anim.setDuration(ms)
    anim.setEasingCurve(curve)
    if done:
        anim.finished.connect(done)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def fade(widget: QWidget, to: float, ms: int = MEDIUM, start: float | None = None, done=None):
    """Fade `widget` to an opacity; at 1 the effect is removed so text renders as usual."""
    def finish():
        if to >= 1.0:
            widget.setGraphicsEffect(None)
        if done:
            done()

    if not on():
        finish()
        return None
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        eff.setOpacity(1.0 if start is None else start)
        widget.setGraphicsEffect(eff)
    elif start is not None:
        eff.setOpacity(start)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setStartValue(eff.opacity())
    anim.setEndValue(to)
    return _run(anim, ms, done=finish)


def slide_width(widget: QWidget, to: int, ms: int = MEDIUM, done=None):
    """Open or close a side panel by animating its maximum width (to is 0 to close)."""
    if not on():
        widget.setMaximumWidth(to if to else 0)
        if done:
            done()
        return None
    anim = QPropertyAnimation(widget, b"maximumWidth", widget)
    anim.setStartValue(widget.width() if widget.isVisible() else 0)
    anim.setEndValue(to)
    return _run(anim, ms, done=done)


class Clock(QObject):
    """One 30 Hz tick for everything that paints its own motion. It runs only while someone
    holds it (`hold`/`release`), motion is on, and `shown` (the window is on screen)."""

    tick = Signal(float)  # seconds since the clock was made

    def __init__(self):
        super().__init__()
        self._holders: set[int] = set()
        self._t0 = time.monotonic()
        self.shown = True
        self._timer = QTimer(self, interval=33, timeout=lambda: self.tick.emit(self.now()))

    def now(self) -> float:
        return time.monotonic() - self._t0

    def hold(self, who: object) -> None:
        self._holders.add(id(who))
        self._update()

    def release(self, who: object) -> None:
        self.release_key(id(who))

    def release_key(self, key: int) -> None:
        self._holders.discard(key)
        self._update()

    def holds(self, who: object) -> bool:
        return id(who) in self._holders

    def set_shown(self, shown: bool) -> None:
        self.shown = shown
        self._update()

    def _update(self):
        run = bool(self._holders) and self.shown and on()
        try:
            if run and not self._timer.isActive():
                self._timer.start()
            elif not run and self._timer.isActive():
                self._timer.stop()
        except RuntimeError:
            pass  # the application is shutting down and Qt has deleted the timer


_clock: list[Clock] = []


def clock() -> Clock:
    if not _clock:
        _clock.append(Clock())
    return _clock[0]


class PulseDot(QWidget):
    """The recording dot: a ring grows out of it every 1.6 s; paused, it blinks slowly in amber."""

    PERIOD = 1.6

    def __init__(self, role: str = "coral", parent=None):
        super().__init__(parent)
        self.role = role
        self.paused = False
        self.setFixedSize(QSize(18, 18))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._t = 0.0
        clock().tick.connect(self._on_tick)
        key = id(self)
        self.destroyed.connect(lambda _o=None: clock().release_key(key))  # closed without being hidden

    def _on_tick(self, t: float):
        if self.isVisible():
            self._t = t
            self.update()

    def showEvent(self, e):
        clock().hold(self)
        super().showEvent(e)

    def hideEvent(self, e):
        clock().release(self)
        super().hideEvent(e)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(self.rect()).center()
        r = 4.0
        color = theme.color("amber" if self.paused else self.role)
        moving = on()
        phase = (self._t % self.PERIOD) / self.PERIOD
        if self.paused:
            if moving:
                color.setAlphaF(0.4 + 0.6 * (0.5 + 0.5 * math.cos(2 * math.pi * phase)))
        elif moving:
            ring = QColor(color)
            ring.setAlphaF(0.55 * (1 - phase))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring)
            rr = r + 5 * phase
            p.drawEllipse(c, rr, rr)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(c, r, r)
        p.end()


class Ripple(QWidget):
    """A ring that grows from a button and fades: the button did something. Child of the button."""

    def __init__(self, button: QWidget, role: str = "coral"):
        super().__init__(button)
        self.role = role
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._p = 1.0
        self.hide()

    def play(self):
        if not on():
            return
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        from PySide6.QtCore import QVariantAnimation

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.valueChanged.connect(self._frame)
        anim.finished.connect(self.hide)
        _run(anim, 900, QEasingCurve.Type.OutCubic)

    def _frame(self, v):
        self._p = float(v)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(self.rect()).center()
        base = min(self.width(), self.height()) / 2 - 6
        color = theme.color(self.role)
        color.setAlphaF(0.7 * (1 - self._p))
        pen = p.pen()
        pen.setColor(color)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rr = base * (0.5 + 0.6 * self._p)
        p.drawEllipse(c, rr, rr)
        p.end()

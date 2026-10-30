"""Motion: when it runs, that it ends where a jump would, and that it can be turned off."""

from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel

from echo_app import settings
from echo_app.ui import motion
from test_ui import _transcribed, lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures


def test_desktop_and_setting_turn_motion_off(monkeypatch, tmp_path):
    monkeypatch.delenv("ECHO_REDUCE_MOTION")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    (tmp_path / "kdeglobals").write_text("[KDE]\nAnimationDurationFactor=0\n")
    assert motion._ask_desktop() is False
    (tmp_path / "kdeglobals").write_text("[KDE]\nAnimationDurationFactor=0.5\n")
    assert motion._ask_desktop() is True
    monkeypatch.setattr(motion, "_desktop", [True])
    assert motion.enabled()
    cfg, _ = settings.load()
    cfg.reduce_motion = True
    settings.save(cfg)
    assert not motion.enabled()
    monkeypatch.setenv("ECHO_REDUCE_MOTION", "1")
    cfg.reduce_motion = False
    settings.save(cfg)
    assert not motion.enabled() and not motion.on()


def test_helpers_end_where_a_jump_would(qapp, monkeypatch):
    w = QLabel("x")
    w.show()
    motion.fade(w, 1.0, start=0.0)  # off: no effect left behind
    assert w.graphicsEffect() is None
    monkeypatch.setenv("ECHO_REDUCE_MOTION", "0")
    monkeypatch.setattr(motion, "_desktop", [True])
    motion.refresh()
    motion.fade(w, 1.0, 120, start=0.0)
    assert isinstance(w.graphicsEffect(), QGraphicsOpacityEffect)
    assert wait_until(lambda: w.graphicsEffect() is None, 2)  # removed at the end: sharp text at rest
    w.setMaximumWidth(300)
    motion.slide_width(w, 0, 120)
    assert wait_until(lambda: w.maximumWidth() == 0, 2)


def test_window_with_motion(window, lib, tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_REDUCE_MOTION", "0")
    monkeypatch.setattr(motion, "_desktop", [True])
    motion.refresh()
    rec = _transcribed(lib, tmp_path)
    window._refresh()
    assert window.model.born.get(rec.id) is not None and window.model.needs_frames()
    assert motion.clock().holds(window.list) and motion.clock()._timer.isActive()  # frames while it arrives
    window.list.viewport().grab()
    pump(500)
    window._refresh()
    assert not window.model.needs_frames() and not motion.clock().holds(window.list)
    window._select(rec.id)
    window.show_details(True)
    assert window.details.isVisible()
    assert wait_until(lambda: window.details.width() == window.details.WIDTH, 2)
    window.show_details(False)
    assert window.details.isVisible()  # sliding closed
    assert wait_until(lambda: not window.details.isVisible(), 2)
    window.show_message("Hola", 200)
    assert window.toast.isVisible()
    assert wait_until(lambda: not window.toast.isVisible(), 3)
    panel = window.recorder_panel
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    assert panel.pulse.isVisible() and motion.clock().holds(panel.pulse)  # the dot pulses
    panel.add_marker()
    assert panel._ripple.isVisible()
    panel.stop()
    assert wait_until(lambda: not panel.pulse.isVisible()) and not motion.clock().holds(panel.pulse)
    window._set_shown(False)
    assert not motion.clock()._timer.isActive()  # nothing moves while hidden
    window._set_shown(True)

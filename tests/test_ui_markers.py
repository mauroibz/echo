"""Markers in the window: while recording, on the waveform, and in the transcript margin."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from echo_app import importer
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures


def test_mark_while_recording_with_a_note(window, lib):
    panel = window.recorder_panel
    assert not window.a_mark.isEnabled()
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    assert window.a_mark.isEnabled() and window.tray_mark.isEnabled()
    pump(800)
    window.a_mark.trigger()
    assert panel.note.isVisible()
    panel.note.setText("acá empieza lo importante")
    panel.note.returnPressed.emit()
    assert not panel.note.isVisible()
    sess = panel.session
    assert wait_until(lambda: [m["note"] for m in sess.markers()] == ["acá empieza lo importante"], 3)
    panel.stop()
    assert wait_until(lambda: lib.all() and lib.all()[0].meta.state == "ready", 20)
    m = lib.all()[0].meta.markers
    assert len(m) == 1 and 0.5 < m[0]["at"] < 2.0


def test_note_field_closes_by_itself(window, lib, monkeypatch):
    from echo_app.ui import recorder_panel

    panel = window.recorder_panel
    panel._note_timer.setInterval(200)
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    pump(500)
    panel.add_marker()
    assert panel.note.isVisible()
    assert wait_until(lambda: not panel.note.isVisible(), 3)
    assert recorder_panel.NOTE_IDLE_MS == 10_000


def test_markers_on_the_waveform(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(200)
    wave = window.player.wave
    wave.add_marker(1.0)
    wave.add_marker(3.0)
    assert [m["at"] for m in lib.get(rec.id).meta.markers] == [1.0, 3.0]
    # Next / previous marker.
    window.player.seek(0.0)
    window.player.jump_marker(1)
    assert abs(window.player.player.position() - 1.0) < 0.01
    window.player.jump_marker(1)
    assert abs(window.player.player.position() - 3.0) < 0.01
    window.player.seek(3.5)
    window.player.jump_marker(-1)
    assert abs(window.player.player.position() - 1.0) < 0.01
    # Drag the second marker with the mouse (Shift: no snapping to pauses).
    x3, x2 = wave._x(3.0), wave._x(2.5)
    shift = Qt.KeyboardModifier.ShiftModifier
    for kind, x in ((QMouseEvent.Type.MouseButtonPress, x3), (QMouseEvent.Type.MouseMove, x2),
                    (QMouseEvent.Type.MouseButtonRelease, x2)):
        ev = QMouseEvent(kind, QPointF(x, 3), QPointF(x, 3), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, shift)
        {QMouseEvent.Type.MouseButtonPress: wave.mousePressEvent, QMouseEvent.Type.MouseMove: wave.mouseMoveEvent,
         QMouseEvent.Type.MouseButtonRelease: wave.mouseReleaseEvent}[kind](ev)
    ats = [m["at"] for m in lib.get(rec.id).meta.markers]
    assert ats[0] == 1.0 and abs(ats[1] - 2.5) < 0.05
    wave.remove_marker(0)
    assert len(lib.get(rec.id).meta.markers) == 1
    wave.grab()  # paints the flags


def test_marker_dots_in_the_transcript(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    rec.set_markers([{"at": 2.5, "note": "segunda"}])
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    margin = tp.editor.margin
    assert margin.isVisible() and [(pos, m["note"]) for pos, m in margin.marks] == [(13, "segunda")]
    assert not margin.stamps  # times are off; the margin is just the marker column
    played = []
    tp.marker_clicked.connect(played.append)
    rect, _m = margin._dots()[0]
    margin.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(rect.center()),
                                       QPointF(rect.center()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                       Qt.KeyboardModifier.NoModifier))
    assert played == [2.5]
    window.player.wave.add_marker(0.5)  # a new marker on the waveform appears in the margin
    assert len(margin.marks) == 2

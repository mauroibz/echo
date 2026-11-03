"""The recording dock: record, mark, pause and stop without the window."""

from echo_app.ui import record_dock
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures


def test_record_from_the_dock(window, lib, monkeypatch):
    window.toggle_dock()
    dock = window.dock
    assert dock.isVisible() and not window.isVisible()
    dock.refresh()
    assert dock.state == "rest" and dock.record.isVisible() and dock.input_name.text()
    assert not dock.time.isVisible() and not dock.open_btn.isVisible()
    dock.record.click()
    assert wait_until(lambda: window.recorder_panel.session is not None)
    dock.refresh()
    assert dock.state == "recording" and dock.time.isVisible() and dock.pause.isVisible()
    dock.mark.click()
    pump(1100)  # two markers at the same point of the audio are kept as one
    dock.mark.click()
    assert dock.mark.text() == "2" and not window.recorder_panel.note.isVisible()  # no note field
    window.recorder_panel.toggle_pause()
    assert wait_until(lambda: (dock.refresh(), dock.pulse.paused)[1], 5)
    window.recorder_panel.toggle_pause()
    # Away from the pointer for a while, it shrinks to the time.
    monkeypatch.setattr(record_dock, "MINIMAL_AFTER_S", 0.0)
    dock._hovered = False
    dock._hover_left -= 1
    dock.refresh()
    assert not dock.info.isVisible(), dock.message.text()  # no problem shown
    assert dock.minimal and dock.time.isVisible() and not dock.pause.isVisible()
    monkeypatch.setattr(record_dock, "MINIMAL_AFTER_S", 5.0)
    dock._hovered = True
    dock.refresh()
    assert not dock.minimal and dock.pause.isVisible()
    rid = window.recorder_panel.session.rec.id
    dock.record.click()  # Stop
    assert wait_until(lambda: (dock.refresh(), dock.state)[1] == "saved", 10)
    assert dock.open_btn.isVisible() and dock.message.text().startswith("Saved") and dock.saved_id == rid
    assert wait_until(lambda: lib.get(rid).meta.state == "ready", 20)
    assert len(lib.get(rid).meta.markers) == 2
    dock.open_btn.click()
    assert window.isVisible() and not dock.isVisible() and window.current().id == rid
    assert window.state.get("dock_pos") is not None


def test_closing_while_recording_shows_the_dock(window):
    panel = window.recorder_panel
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    window.close()
    assert not window.isVisible() and window.dock.isVisible() and panel.session is not None
    window.dock.done_btn.click()  # only in the saved state; here nothing happens
    window.toggle_dock()
    assert window.isVisible() and not window.dock.isVisible()
    panel.stop()
    assert wait_until(lambda: panel.session is None)


def test_notes_drop_down_from_the_dock(window, lib):
    panel = window.recorder_panel
    window.toggle_dock()
    dock = window.dock
    dock.refresh()
    assert not dock.notes_btn.isVisible()  # only while recording
    dock.record.click()
    assert wait_until(lambda: panel.session is not None)
    rid = panel.session.rec.id
    lib.get(rid).update(notes="Antes de empezar")
    dock.refresh()
    assert dock.notes_btn.isVisible() and not dock.notes_card.isVisible()
    dock.notes_btn.click()
    assert dock.notes_card.isVisible() and dock.notes.toPlainText() == "Antes de empezar"
    dock.notes.setPlainText("Antes de empezar\nPrecio: revisar el plan anual")
    assert wait_until(lambda: lib.get(rid).meta.notes.endswith("plan anual"), 3)  # saved as typed
    dock._hovered, dock._hover_left = False, 0.0
    dock.refresh()
    assert not dock.minimal  # stays open while the notes are
    dock.notes.setPlainText("Antes de empezar\nPrecio: revisar el plan anual\nLlamar a Ana")
    window.toggle_dock()  # back to the window before the save ran: kept all the same
    assert lib.get(rid).meta.notes.endswith("Llamar a Ana")
    assert window.player.notes.toPlainText().endswith("Llamar a Ana")  # the window shows them, not its old copy
    window.toggle_dock()
    panel.stop()
    assert wait_until(lambda: (dock.refresh(), dock.state)[1] == "saved", 10)
    assert not dock.notes_btn.isChecked() and not dock.notes_card.isVisible()


def test_switch_to_the_dock_when_recording(window, lib):
    from echo_app import settings

    s = settings.load()[0]
    s.dock_when_recording = True
    settings.save(s)
    panel = window.recorder_panel
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    assert wait_until(lambda: window.dock.isVisible() and not window.isVisible(), 3)
    panel.stop()
    assert wait_until(lambda: panel.session is None)
    window.toggle_dock()
    assert window.isVisible()
    panel.start(quick_note=True)  # a quick note leaves the window as it is
    assert wait_until(lambda: panel.session is not None)
    pump(300)
    assert window.isVisible() and not window.dock.isVisible()
    panel.stop()
    assert wait_until(lambda: panel.session is None)

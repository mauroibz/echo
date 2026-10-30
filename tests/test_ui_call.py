"""Recording a call from the window: the computer-audio toggle, its meter, and the two-track result."""

import sys

from echo_app import settings
from echo_app.audio import backend, pipewire
from test_ui import FAKE, lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures


def test_toggle_records_a_call_with_two_meters(window, lib, monkeypatch):
    monkeypatch.setenv("ECHO_CAPTURE_OUT_CMD", f"{sys.executable} -P {FAKE} {{path}} {{bps}} negative")
    panel = window.recorder_panel
    # In the input panel under Record; while recording, the block shows the second meter.
    inputs = panel.input_panel
    assert panel.computer_row.isVisibleTo(inputs) and not panel.computer.isChecked()
    assert not panel.out_meter.isVisibleTo(inputs)
    panel.computer.setChecked(True)
    assert settings.load()[0].computer_audio and panel.out_meter.isVisibleTo(inputs)
    assert "computer audio" in panel.source_btn.text()
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    assert not panel.computer.isEnabled()
    assert panel.call_meter.isVisibleTo(panel)
    assert wait_until(lambda: panel.out_meter._level > -60, 5), "the computer-audio meter moves"
    pump(800)
    panel.stop()
    assert wait_until(lambda: lib.all() and lib.all()[0].meta.state == "ready", 20)
    rec = lib.all()[0]
    assert rec.meta.channels == 2 and rec.meta.tracks == ["mic", "computer"]
    assert wait_until(lambda: panel.computer.isEnabled())
    assert wait_until(lambda: window.player.play_btn.isEnabled(), 3)
    assert window.player._rec_player.mix


def test_toggle_hidden_for_a_monitor_and_without_output_recording(window, monkeypatch):
    panel = window.recorder_panel
    mon = pipewire.Source("speakers", "Speakers", pipewire.MONITOR, 2, True)
    panel._sources = [*panel._sources, mon]
    panel.source.addItem(mon.short_label, mon.name)
    panel.source.setCurrentIndex(panel.source.count() - 1)
    panel._source_chosen(panel.source.currentIndex())
    assert panel.computer_row.isHidden()
    panel.source.setCurrentIndex(0)
    panel._source_chosen(0)
    assert not panel.computer_row.isHidden()
    monkeypatch.setattr(backend.CommandBackend, "records_outputs", False)
    panel._show_computer_row()
    assert panel.computer_row.isHidden() and not panel.computer_audio_on()

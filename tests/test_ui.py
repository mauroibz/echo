"""UI tests driving real widgets offscreen (no pytest-qt dependency)."""

import json
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QMimeData, QPointF, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from echo_app import importer, settings  # noqa: E402
from echo_app.library import EDITED, TRANSCRIPT, Library  # noqa: E402

FAKE = Path(__file__).with_name("fake_capture.py")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(["echo-test"])
    yield app


def pump(ms=50):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(cond, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump(50)
        if cond():
            return True
    return False


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_CAPTURE_CMD", f"{sys.executable} -P {FAKE} {{path}} {{bps}}")
    s = settings.Settings(auto_transcribe=False)
    settings.save(s)
    return Library(tmp_path / "data")


@pytest.fixture
def window(qapp, lib, monkeypatch):
    from echo_app.audio import pipewire
    from echo_app.ui import common
    from echo_app.ui.main_window import MainWindow

    monkeypatch.setattr(pipewire, "list_sources", lambda: [pipewire.Source("fake", "Test mic", pipewire.INPUT, 1, True)])
    st = common.UiState()
    st.data = {}
    w = MainWindow(lib, st)
    w.recorder_panel.set_window_active(False)  # no idle monitor stream in tests
    w.show()
    pump(200)
    yield w
    if w.recorder_panel.session is not None:
        w.recorder_panel.stop()
        wait_until(lambda: not any(r.meta.state == "recording" for r in lib.all()), 20)
    w._quitting = True
    w.shutdown()
    w.close()
    pump(50)


def wav(path, seconds=1.0, freq=440):
    import subprocess

    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=f={freq}:d={seconds}", str(path)],
                   check=True)
    return path


def test_empty_state_then_drop_import(window, lib, tmp_path):
    assert window.empty.isVisible()
    f1 = wav(tmp_path / "PTT-20261023-WA0001.opus")
    f2 = wav(tmp_path / "nota.mp3", freq=300)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(f1)), QUrl.fromLocalFile(str(f2)), QUrl("https://example.com/a.mp3")])
    ev = QDropEvent(QPointF(100, 100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier)
    window.dropEvent(ev)
    assert wait_until(lambda: window.model.rowCount() == 2)
    assert not window.empty.isVisible()
    assert window.current() is not None
    titles = {window.model.recording(r).meta.title for r in range(2)}
    assert "nota" in titles and any(t.startswith("WhatsApp voice note") for t in titles)


def test_record_from_window(window, lib):
    window.recorder_panel.start()
    assert wait_until(lambda: window.recorder_panel.session is not None)
    assert wait_until(lambda: window.windowTitle().startswith("● Recording"))
    pump(1500)
    window.recorder_panel.toggle_pause()
    assert wait_until(lambda: window.recorder_panel.state_label.text() == "Paused")
    window.recorder_panel.toggle_pause()
    pump(500)
    window.recorder_panel.stop()
    assert wait_until(lambda: lib.all() and lib.all()[0].meta.state == "ready", 20)
    assert wait_until(lambda: window.windowTitle() == "Echo")
    rec = lib.all()[0]
    assert rec.meta.duration > 1.0
    assert window.current().id == rec.id
    assert wait_until(lambda: window.player.play_btn.isEnabled(), 3)


def _transcribed(lib, tmp_path):
    rec = importer.import_file(lib, wav(tmp_path / "t.wav", 4)).recording
    segs = [{"start": 0.0, "end": 1.5, "text": "Hola mundo.", "paragraph": True},
            {"start": 2.0, "end": 3.9, "text": "Segunda parte.", "paragraph": True}]
    rec.path(TRANSCRIPT).write_text(json.dumps({"text": "Hola mundo.\n\nSegunda parte.", "segments": segs,
                                                "created": "2026-10-23T10:00:00-03:00",
                                                "model": {"adapter_enabled": True}}))
    return rec


def test_editor_shows_autosaves_and_reverts(window, lib, tmp_path, monkeypatch):
    rec = _transcribed(lib, tmp_path)
    other = importer.import_file(lib, wav(tmp_path / "o.wav", 1, 600)).recording
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    assert tp.has_text() and tp.editor.toPlainText() == "Hola mundo.\n\nSegunda parte."
    assert "Model transcript" in tp.status.text()
    tp.editor.moveCursor(tp.editor.textCursor().MoveOperation.End)
    tp.editor.insertPlainText(" Fin.")
    assert wait_until(lambda: rec.path(EDITED).exists(), 3)  # autosave within the spec's 2 s
    assert rec.text().endswith("Fin.")
    # Edit then switch immediately: saved on switch.
    tp.editor.insertPlainText(" Más.")
    window._select(other.id)
    assert rec.text().endswith("Más.")
    window._select(rec.id)
    pump(100)
    assert tp.editor.toPlainText().endswith("Más.") and tp.status.text().startswith("Edited")
    tp.revert(confirm=False)
    assert not rec.path(EDITED).exists() and tp.editor.toPlainText() == "Hola mundo.\n\nSegunda parte."
    tp.editor.undo()  # revert is undoable
    assert tp.editor.toPlainText().endswith("Más.")


def test_follow_along_and_ctrl_click(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    tp.follow(2.5)
    assert tp._current_span == 1
    seeks = []
    tp.seek_requested.connect(seeks.append)
    tp._on_ctrl_click(3)
    assert seeks == [0.0]


def test_find_is_accent_insensitive(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    rec.save_edited("La reunión empezó. Otra REUNION más.")
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    tp.open_find()
    tp.find_edit.setText("reunion")
    assert len(tp._find_matches) == 2 and tp.find_count.text() == "1 of 2"


def test_search_filters_by_transcript(window, lib, tmp_path):
    _transcribed(lib, tmp_path)
    importer.import_file(lib, wav(tmp_path / "otro.wav", 1, 700))
    window.model.refresh()
    window.search.setText("segunda")
    assert wait_until(lambda: window.model.rowCount() == 1)
    window.search.setText("")
    assert wait_until(lambda: window.model.rowCount() == 2)


def test_status_shows_transcription_progress(window, lib, tmp_path):
    from echo_app.fsutil import atomic_write_json
    from echo_app.library import PROGRESS, REQUESTED

    rec = importer.import_file(lib, wav(tmp_path / "p.wav")).recording
    atomic_write_json(rec.path(REQUESTED), {"requested": 1})
    atomic_write_json(rec.path(PROGRESS), {"stage": "transcribing", "done": 5, "total": 10, "eta_s": 30})
    window._refresh()
    from echo_app.ui.library_view import ROLE_STATUS

    st = window.model.data(window.model.index(window.model.row_of(rec.id)), ROLE_STATUS)
    assert st.text.startswith("Transcribing 50%") and st.progress == 0.5


def test_crop_from_waveform_is_saved(window, lib, tmp_path):
    rec = importer.import_file(lib, wav(tmp_path / "c.wav", 4)).recording
    window._select(rec.id)
    pump(100)
    window.player.wave._set_handle("start", 1.0)
    window.player.wave._set_handle("end", 3.0)
    again = lib.get(rec.id)
    assert again.meta.crop_start == 1.0 and again.meta.crop_end == 3.0
    assert window.player.crop_label.text() == "Crop 0:01–0:03"
    window.player.clear_crop()
    assert lib.get(rec.id).meta.crop_start is None


def test_delete_moves_to_trash(window, lib, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    rec = importer.import_file(lib, wav(tmp_path / "d.wav")).recording
    window._select(rec.id)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.delete_selected()
    assert lib.get(rec.id) is None and window.model.rowCount() == 0


def test_settings_dialog_roundtrip(qapp, lib):
    from echo_app.ui.dialogs import SettingsDialog

    d = SettingsDialog(recording_active=False)
    d.rate.setCurrentIndex(d.rate.findData(44100))
    d.channels.setCurrentIndex(d.channels.findData(2))
    d.auto.setChecked(True)
    d.accept()
    cfg, _ = settings.load()
    assert cfg.sample_rate == 44100 and cfg.channels == 2 and cfg.auto_transcribe


def test_single_instance_forwarding(qapp, tmp_path):
    from echo_app.ui import app as uiapp

    got = []
    server = uiapp.InstanceServer(got.append)
    try:
        assert uiapp.forward_to_running([str(tmp_path / "x.opus")])
        assert wait_until(lambda: got, 5)
        assert got[0]["show"] and got[0]["files"] == [str(tmp_path / "x.opus")]
    finally:
        server.close()
    assert not uiapp.forward_to_running([])


def test_welcome_and_doctor_dialogs_build(qapp, window):
    from echo_app.ui.dialogs import DoctorDialog, WelcomeDialog

    w = WelcomeDialog(window.recorder_panel, window)
    assert w.source.count() >= 1
    w.done(0)
    d = DoctorDialog(window)
    assert wait_until(lambda: d.copy_btn.isEnabled(), 60)
    d.reject()

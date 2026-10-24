"""Quick notes, the record toggle and titles from the first sentence."""

import json
import sys
import threading
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

from echo_app import cli, recorder, settings
from echo_app.library import Library, auto_title
from echo_app.worker.planning import join_text
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures

FAKE = Path(__file__).with_name("fake_capture.py")


def test_auto_title():
    assert auto_title("Hola, me llamo Mauro. Y esto sigue.") == "Hola, me llamo Mauro"
    assert auto_title("¿Qué hacemos mañana? Bueno.") == "Qué hacemos mañana"
    long = "una frase larga sin punto que sigue y sigue hablando de muchas cosas sin parar nunca"
    assert auto_title(long) == "una frase larga sin punto que sigue y sigue hablando de"
    assert auto_title("") == "" and auto_title("...") == ""


def _transcribe(rec, text):
    """What the worker does at the end of a job, without a model."""
    from echo_app.worker import service

    class Engine:
        device, batch_size = "stub", 4

        def load(self):
            pass

        def speech_regions(self, audio, progress=None):
            return [(0.2, 0.8)]

        def transcribe(self, clips, adapter=True, context=None, language="es"):
            return [text for _ in clips]

        def model_info(self, adapter, language="es"):
            return {"base": "stub", "adapter": None, "adapter_enabled": False, "device": "stub"}

    rec.request_transcription()
    service.Worker(Library(rec.folder.parent.parent), Engine()).process(rec)


def test_generated_titles_follow_the_transcript_until_renamed(tmp_path):
    from echo_app import importer

    lib_ = Library(tmp_path / "data")
    rec = importer.import_file(lib_, wav(tmp_path / "n.wav", 1)).recording
    rec.update(title="Recording 2026-10-24 10:00", title_auto=True)
    _transcribe(rec, "Comprar pan y llamar a Ana. Después el resto.")
    assert rec.reload().meta.title == "Comprar pan y llamar a Ana"
    rec.update(title="Mi título", title_auto=False)
    _transcribe(rec, "Otra cosa distinta.")
    assert rec.reload().meta.title == "Mi título"


def test_imports_keep_their_title(tmp_path):
    from echo_app import importer

    lib_ = Library(tmp_path / "data")
    rec = importer.import_file(lib_, wav(tmp_path / "entrevista.wav", 1)).recording
    assert not rec.meta.title_auto
    _transcribe(rec, "Hola a todos.")
    assert rec.reload().meta.title == "entrevista"


def test_cli_toggle_and_quick_note(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ECHO_CAPTURE_CMD", f"{sys.executable} -P {FAKE} {{path}} {{bps}}")
    settings.save(settings.Settings(data_dir=str(tmp_path / "data"), sample_rate=16000, auto_transcribe=False))
    lib_ = Library(tmp_path / "data")
    assert cli.main(["record", "--toggle"]) == 0
    s = recorder.active(lib_)
    assert s is not None and s.rec.meta.title_auto and not s.rec.meta.quick_note
    time.sleep(0.8)
    assert cli.main(["record", "--toggle"]) == 0  # the same command stops it
    assert recorder.active(lib_) is None and lib_.get(s.rec.id).meta.state == "ready"
    assert cli.main(["record", "--quick-note"]) == 0
    q = recorder.active(lib_)
    assert q.rec.meta.quick_note and q.rec.meta.tags == ["nota"]
    time.sleep(0.8)

    def transcribed_later():
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            rec = lib_.get(q.rec.id)
            if rec and rec.meta.state == "ready":
                segs = [{"start": 0.0, "end": 0.8, "text": "Comprar pan.", "paragraph": True}]
                rec.path("transcript.json").write_text(json.dumps({"segments": segs, "text": join_text(segs),
                                                                   "created": "x"}))
                return
            time.sleep(0.1)

    t = threading.Thread(target=transcribed_later)
    t.start()
    capsys.readouterr()
    assert cli.main(["record", "--quick-note", "--wait"]) == 0
    t.join()
    assert capsys.readouterr().out.strip().endswith("Comprar pan.")
    assert not lib_.get(q.rec.id).meta.quick_note  # delivered once


def test_window_copies_a_quick_note_when_ready(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    rec.update(quick_note=True)
    window._refresh()  # first sight of the recording
    pump(50)
    rec.update(title="otra")  # any change after transcription
    window._refresh()
    assert QApplication.clipboard().text() == "Hola mundo.\n\nSegunda parte.\n"
    assert not lib.get(rec.id).meta.quick_note


def test_quick_note_shortcut_starts_and_stops(window, lib):
    window._global_shortcut("quick-note")
    assert wait_until(lambda: window.recorder_panel.session is not None)
    meta = window.recorder_panel.session.rec.meta
    assert meta.quick_note and meta.tags == ["nota"]
    pump(600)
    window._global_shortcut("quick-note")
    assert wait_until(lambda: lib.all() and all(r.meta.state == "ready" for r in lib.all()), 20)
    assert wait_until(lambda: window.recorder_panel.session is None)
    window._global_shortcut("record-toggle")
    assert wait_until(lambda: window.recorder_panel.session is not None)
    assert not window.recorder_panel.session.rec.meta.quick_note

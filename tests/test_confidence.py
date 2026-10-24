"""Passages to check: flags from the engine, the relative low-confidence rule, the editor marks."""

import json

from echo_app import importer
from echo_app.worker import service
from echo_app.worker.service import Worker
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures
from test_worker import StubEngine, speechy_wav


class FlaggingEngine(StubEngine):
    """Passage 2 comes back short after retries; passage 4 the model was unsure of."""

    def transcribe_flagged(self, clips, adapter=True, context=None, language="es"):
        out = []
        for c in clips:
            n = len(self.calls)
            self.calls.append([len(c)])
            flags = ["retried", "short"] if n == 2 else []
            out.append((f"texto {n}", flags, -0.5 if n == 4 else -0.05 - 0.001 * n))
        return out


def test_flags_and_low_confidence_in_the_transcript(tmp_path):
    from echo_app.library import Library

    lib = Library(tmp_path / "data")
    pattern = []
    for _ in range(7):
        pattern += [(20, True), (3, False)]  # each its own passage
    rec = importer.import_file(lib, speechy_wav(tmp_path / "f.wav", pattern)).recording
    rec.request_transcription()
    eng = FlaggingEngine()
    eng.batch_size = 1
    Worker(lib, eng).process(rec)
    t = rec.transcript()
    assert t["version"] == 2
    flags = {s["text"]: s["flags"] for s in t["segments"]}
    assert flags["texto 2"] == ["retried", "short"] and flags["texto 4"] == ["low"]
    assert sum(1 for f in flags.values() if f) == 2
    assert all("logprob" in s for s in t["segments"])


def test_low_rule_needs_enough_passages():
    segs = [{"text": "a", "logprob": -0.1, "flags": []}, {"text": "b", "logprob": -2.0, "flags": []}]
    service.mark_low(segs)
    assert not any(s["flags"] for s in segs)


def test_version_1_transcripts_and_old_partials_still_work(tmp_path):
    from echo_app.library import Library

    lib = Library(tmp_path / "data")
    rec = importer.import_file(lib, speechy_wav(tmp_path / "o.wav", [(1, False), (5, True), (1, False)])).recording
    rec.request_transcription()
    eng = StubEngine()  # an engine without flags
    Worker(lib, eng).process(rec)
    assert rec.transcript()["segments"][0]["flags"] == []


def _flagged(lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    t = json.loads(rec.path("transcript.json").read_text())
    t["segments"][1]["flags"] = ["short"]
    rec.path("transcript.json").write_text(json.dumps(t))
    return rec


def test_editor_marks_and_clears_on_edit(window, lib, tmp_path):
    rec = _flagged(lib, tmp_path)
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    assert [(a, b) for a, b, _s in tp._flagged] == [(13, 27)]
    assert "1 passage to check" in tp.status.text()
    assert "very few words for 2 s" in tp._tooltip(15)
    assert tp._tooltip(2) is None
    assert tp.next_flagged() == 2.0 and tp.editor.textCursor().position() == 13
    # Editing the passage clears its mark.
    tp.editor.insertPlainText("Ahora sí: ")
    assert wait_until(lambda: not tp._flagged, 3)
    assert "to check" not in tp.status.text()


def test_list_shows_the_count(window, lib, tmp_path):
    from echo_app.ui.library_view import ROLE_STATUS

    rec = _flagged(lib, tmp_path)
    window._refresh()
    st = window.model.data(window.model.index(window.model.row_of(rec.id)), ROLE_STATUS)
    assert st.text == "Transcribed · ⚑ 1"

"""Merging speakers: one person found twice becomes one speaker, everywhere, and can be separated."""

import json

from echo_app import dictionary, export
from echo_app.index import Index
from test_speaker_search import _lib, meeting
from test_ui import lib, pump, qapp, window  # noqa: F401 - fixtures


def _three(lib):
    rec = meeting(lib, "Weekly", [(1, "Hola."), (2, "Precio uno."), (3, "Precio dos."), (1, "Bien.")], {1: "Pedro"})
    t = json.loads(rec.path("transcript.json").read_text())
    t["speakers"]["centroids"] = {"1": [1.0, 0.0], "2": [0.0, 1.0], "3": [0.0, 0.8]}
    rec.path("transcript.json").write_text(json.dumps(t))
    return rec


def test_merge_names_and_chains(tmp_path):
    lib = _lib(tmp_path)
    rec = _three(lib)
    rec.update(speakers={"1": "Pedro", "3": "Ana"})
    rec.merge_speakers(3, 2)  # 2 had no name: it takes Ana's
    assert rec.meta.speaker_merges == {"3": 2} and rec.meta.speakers == {"1": "Pedro", "2": "Ana"}
    assert [rec.speaker(n) for n in (1, 2, 3, None)] == [1, 2, 2, None]
    rec.merge_speakers(2, 1)  # Pedro keeps his name; 3 follows 2 into 1
    assert rec.meta.speaker_merges == {"3": 1, "2": 1} and rec.meta.speakers == {"1": "Pedro"}
    assert rec.merged_into(1) == [2, 3]
    rec.merge_speakers(3, 1)  # already one: nothing changes
    assert rec.separate_speakers(1) == [2, 3] and rec.meta.speaker_merges == {}
    assert rec.meta.speakers == {"1": "Pedro"}  # the separated are unnamed


def test_exports_index_and_counts_follow(tmp_path):
    lib = _lib(tmp_path)
    rec = _three(lib)
    rec.update(speakers={"1": "Pedro", "2": "Ana"})
    rec.merge_speakers(3, 2)
    # One speaker now: the name is not repeated where Ana goes on.
    assert export.render_transcript(rec, ".txt") == "Pedro: Hola.\n\nAna: Precio uno.\n\nPrecio dos.\n\nPedro: Bien.\n"
    assert export._names(rec) == {1: "Pedro", 2: "Ana"}
    idx = Index(lib)
    idx.sync()
    assert [r["id"] for r in idx.list("@ana dos")] == [rec.id]
    assert idx.speech_matches("@ana dos")[rec.id]["numbers"] == [2]
    idx.close()


def test_a_new_transcription_drops_merges(tmp_path, monkeypatch):
    from echo_app.library import Library
    from test_speakers import _call, _embedder, _process

    lib = Library(tmp_path / "data")
    rec = _call(lib, tmp_path)
    _embedder(monkeypatch, [1])
    _process(lib, rec)
    rec.merge_speakers(2, 1)
    assert rec.meta.speaker_merges == {"2": 1}
    _process(lib, rec)  # numbered afresh: the old merge could join strangers
    assert rec.meta.speaker_merges == {}


def test_menu_merges_labels_follow_and_voice_learns_both(window, lib):
    rec = _three(lib)
    window.model.refresh()
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    assert [n for *_x, n in tp.editor.margin.labels] == [1, 2, 3, 1]
    assert "3 speakers" in tp.status.text()
    tp.merge_speaker(3, 2)
    assert [n for *_x, n in tp.editor.margin.labels] == [1, 2, 1]  # one label where 3 was
    assert "2 speakers" in tp.status.text()
    tp.name_speaker(2, "Ana")
    voice = dictionary.voices()["Ana"]["voice"]
    assert voice == [0.0, 0.9]  # the average of both parts, folded once
    assert tp._speakers_shown() == [1, 2]
    tp.separate_speaker(2)
    assert [n for *_x, n in tp.editor.margin.labels] == [1, 2, 3, 1]
    assert lib.get(rec.id).meta.speakers == {"1": "Pedro", "2": "Ana"}

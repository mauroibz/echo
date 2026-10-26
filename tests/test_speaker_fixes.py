"""Said by: correcting who said a paragraph, or words inside one, and everything following it."""

import json

from echo_app import align, export
from echo_app.index import Index
from echo_app.library import EDITED
from test_speaker_search import _lib, meeting


def _ana_pedro(lib):
    rec = meeting(lib, "Weekly", [(1, "El precio sube ¿cuánto? un diez por ciento."), (2, "Bien."), (2, "Sigo yo.")],
                  {1: "Ana", 2: "Pedro"})
    t = json.loads(rec.path("transcript.json").read_text())
    t["created"] = "2026-10-26T10:00:00-03:00"
    rec.path("transcript.json").write_text(json.dumps(t))
    return rec


def test_pieces_split_relabel_and_ignore_vanished_words():
    segs = [{"text": "Uno dos tres.", "speaker": 1}, {"text": "Cuatro.", "speaker": 2}]
    text = "Uno dos tres. Cuatro."
    spans = align.align(segs, text)
    assert align.speaker_pieces(segs, text, spans) == [(0, 13, 0, 1), (14, 21, 1, 2)]
    fixes = [{"segment": 0, "text": "dos", "speaker": 2}, {"segment": 1, "speaker": 1}]
    assert align.speaker_pieces(segs, text, spans, fixes) == [(0, 3, 0, 1), (4, 7, 0, 2), (8, 13, 0, 1),
                                                              (14, 21, 1, 1)]
    gone = [{"segment": 0, "text": "cinco", "speaker": 2}]
    assert align.speaker_pieces(segs, text, spans, gone) == [(0, 13, 0, 1), (14, 21, 1, 2)]


def test_split_in_exports_with_estimated_times_and_search(tmp_path):
    lib = _lib(tmp_path)
    rec = _ana_pedro(lib)
    # As the window does it: breaks around the words, then the fix.
    rec.path(EDITED).write_text("El precio sube\n\n¿cuánto?\n\nun diez por ciento.\n\nBien.\n\nSigo yo.")
    rec.fix_speaker(0, 2, "¿cuánto?", 0.4, 0.6)
    assert export.render_transcript(rec, ".txt") == \
        "Ana: El precio sube\n\nPedro: ¿cuánto?\n\nAna: un diez por ciento.\n\nPedro: Bien.\n\nSigo yo.\n"
    cues = export.cues(rec)
    assert [c[2] for c in cues[:3]] == ["El precio sube", "¿cuánto?", "un diez por ciento."]
    assert 0.0 < cues[1][0] < cues[1][1] < 1.5 and cues[0][0] == 0.0 and cues[2][1] == 1.5
    idx = Index(lib)
    idx.sync()
    assert [r["id"] for r in idx.list("@pedro cuanto")] == [rec.id] and idx.list("@ana cuanto") == []
    idx.close()
    f = rec.meta.speaker_fixes[0]
    assert f == {"transcript": "2026-10-26T10:00:00-03:00", "segment": 0, "speaker": 2, "name": "Pedro",
                 "text": "¿cuánto?", "start": 0.4, "end": 0.6}


def test_relabel_someone_new_undo_and_old_transcripts(tmp_path):
    lib = _lib(tmp_path)
    rec = _ana_pedro(lib)
    rec.fix_speaker(2, 3)  # "Sigo yo." was someone new
    rec.update(speakers={**rec.meta.speakers, "3": "Luis"})
    assert rec.speaker_numbers() == [1, 2, 3] and export._names(rec) == {1: "Ana", 2: "Pedro", 3: "Luis"}
    assert export.render_transcript(rec, ".txt").endswith("Pedro: Bien.\n\nLuis: Sigo yo.\n")
    rec.fix_speaker(2, 1)  # changed again: one fix per passage
    assert len(rec.meta.speaker_fixes) == 1 and rec.speaker_at(2, {"speaker": 2}) == 1
    assert rec.unfix_speaker(2) and rec.meta.speaker_fixes == [] and not rec.unfix_speaker(2)
    rec.fix_speaker(2, 1)
    t = json.loads(rec.path("transcript.json").read_text())
    t["created"] = "2026-10-27T10:00:00-03:00"  # transcribed again
    rec.path("transcript.json").write_text(json.dumps(t))
    assert rec.fixes() == [] and len(rec.meta.speaker_fixes) == 1  # kept as data, not applied
    assert export.render_transcript(rec, ".txt").endswith("Pedro: Bien.\n\nSigo yo.\n")

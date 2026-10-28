"""Reassigning passages from the user's "Said by" fixes, from the voiceprints the worker keeps."""

import json

from echo_app import relabel
from echo_app.library import RELABELED, VOICEPRINTS
from test_speaker_fixes import _ana_pedro
from test_speaker_search import meeting
from test_speakers import _voice
from test_ui import lib, pump, qapp, window  # noqa: F401 - fixtures


def _v(seed):
    return list(_voice(seed))


def test_a_fix_brings_the_passages_that_sound_like_it():
    # Speaker 1 is two people: passages 0-3 one voice, 4-5 another, which the user names in 4.
    a, b, c = 1, 2, 3
    prints = {0: _v(a), 1: _v(a), 2: _v(a), 3: _v(a), 4: _v(b), 5: _v(b), 6: _v(c), 7: _v(c)}
    labels = [1, 1, 1, 1, 1, 1, 2, 2, 1]
    out = relabel.reassign(labels, prints, {4: 3})
    assert out[:8] == [1, 1, 1, 1, 3, 3, 2, 2]
    assert out[8] == 1  # no voiceprint, and the passage before it did not move
    # A short passage that had its speaker from the passage before follows it.
    assert relabel.reassign(labels[:6] + [1], {**{k: v for k, v in prints.items() if k < 6}}, {4: 3})[6] == 3
    # ...unless segmentation found it was someone else interrupting.
    assert relabel.reassign(labels[:6] + [1], {k: v for k, v in prints.items() if k < 6}, {4: 3}, None, [6])[6] == 1
    # Without a fix nothing that is clear moves.
    assert relabel.reassign(labels[:8], prints, {})[:4] == [1, 1, 1, 1]


def test_a_call_keeps_each_voice_on_its_track():
    prints = {0: _v(1), 1: _v(2), 2: _v(2)}
    out = relabel.reassign([1, 1, 2], prints, {2: 2}, tracks={1: 0, 2: 1})
    assert out == [1, 1, 2]  # passage 1 sounds like speaker 2, but it is on the microphone


def _with_prints(rec, prints, interrupting=()):
    t = rec.transcript()
    rec.path(VOICEPRINTS).write_text(json.dumps({"transcript": t["created"], "interrupting": list(interrupting),
                                                 "passages": {str(k): v for k, v in prints.items()}}))


def test_relabeling_is_read_over_the_transcript_and_undone(lib):
    rec = _ana_pedro(lib)  # Ana: passage 0; Pedro: 1 and 2. Passage 2 is Ana's voice, in truth.
    t = rec.transcript()
    t["speakers"]["centroids"] = {"1": _v(1), "2": _v(2)}
    rec.path("transcript.json").write_text(json.dumps(t))
    assert relabel.relabel(rec) is None  # no voiceprints: from before they were kept
    _with_prints(rec, {0: _v(1), 1: _v(2), 2: _v(1)})
    rec.fix_speaker(0, 1)
    assert relabel.relabel(rec) == 1
    t = rec.transcript()
    assert [s["speaker"] for s in t["segments"]] == [1, 2, 1] and t["speakers"]["relabeled"]
    assert json.loads(rec.path("transcript.json").read_text())["segments"][2]["speaker"] == 2  # untouched
    assert relabel.relabeled(rec)
    assert relabel.restore(rec) and not rec.path(RELABELED).exists()
    assert [s["speaker"] for s in rec.transcript()["segments"]] == [1, 2, 2]
    # A new transcription makes an old relabeling stale: it is not read.
    relabel.relabel(rec)
    t = json.loads(rec.path("transcript.json").read_text())
    t["created"] = "2026-10-27T10:00:00-03:00"
    rec.path("transcript.json").write_text(json.dumps(t))
    assert [s["speaker"] for s in rec.transcript()["segments"]] == [1, 2, 2]


def test_said_by_moves_what_sounds_the_same_and_can_go_back(window, lib, monkeypatch):
    rec = meeting(lib, "Weekly", [(1, "Hola."), (2, "Bien."), (2, "Sigo yo."), (2, "Otra cosa."), (2, "Y más.")],
                  {1: "Ana", 2: "Pedro"})
    t = rec.transcript()
    t["created"] = "2026-10-26T10:00:00-03:00"
    t["speakers"]["centroids"] = {"1": _v(1), "2": _v(2)}
    rec.path("transcript.json").write_text(json.dumps(t))
    _with_prints(rec, {0: _v(1), 1: _v(1), 2: _v(1), 3: _v(2), 4: _v(2)})  # "Bien. Sigo yo." is Ana
    window.model.refresh()
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    messages = []
    tp.message.connect(messages.append)
    tp.said_by(1, None, tp.editor.toPlainText().index("Bien.") + 1)
    assert [s["speaker"] for s in rec.transcript()["segments"]] == [1, 1, 1, 2, 2]
    assert "1 more passage moved to match what Ana said" in messages[-1]
    assert [n for _a, _name, _c, n in tp.editor.margin.labels] == [1, 2]
    from PySide6.QtWidgets import QMenu

    from echo_app.ui import transcript

    shown = []

    class Menu(QMenu):
        def exec(self, *_a):
            shown.extend(x.text() for x in self.actions())

    monkeypatch.setattr(transcript, "QMenu", Menu)
    tp._speaker_menu(1, None)
    assert "Back to the speakers Echo found" in shown
    tp.restore_speakers()
    assert [s["speaker"] for s in rec.transcript()["segments"]] == [1, 2, 2, 2, 2]
    assert [n for _a, _name, _c, n in tp.editor.margin.labels] == [1, 2]  # "Bien." keeps its fix

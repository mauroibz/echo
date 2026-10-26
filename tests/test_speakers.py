"""Speaker labels: features, clustering, the worker stage, voices, naming and exports."""

import json

import numpy as np
import pytest

from echo_app import dictionary, export, importer
from echo_app.library import Library
from echo_app.worker import speakers
from echo_app.worker.planning import join_text
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures
from test_worker import StubEngine, speechy_wav


def _voice(seed, noise=0.05, rng=np.random.default_rng(0)):
    base = np.random.default_rng(seed).normal(size=256)
    v = base / np.linalg.norm(base) + rng.normal(scale=noise, size=256) / 16
    return v / np.linalg.norm(v)


def test_fbank_shape_and_mean():
    x = (np.sin(np.arange(16000) / 5) * 8000).astype(np.int16)
    f = speakers.fbank(x)
    assert f.shape == (98, 80) and abs(float(f.mean())) < 1e-4
    assert speakers.fbank(np.zeros(100, np.int16)).shape == (0, 80)


def test_cluster_two_voices():
    embs = np.stack([_voice(1) for _ in range(5)] + [_voice(2) for _ in range(4)])
    groups = speakers.cluster(embs)
    assert len(set(groups[:5])) == 1 and len(set(groups[5:])) == 1 and groups[0] != groups[5]


def test_label_numbers_in_order_short_passages_and_monologues():
    passages = [(i * 10.0, i * 10.0 + 9) for i in range(6)]
    embs = {0: _voice(1), 1: _voice(2), 3: _voice(2), 4: _voice(1), 5: _voice(1)}  # passage 2 is short
    labels, centroids = speakers.label(passages, embs)
    assert labels == [1, 2, 2, 2, 1, 1] and set(centroids) == {1, 2}
    assert speakers.label(passages, {i: _voice(1) for i in range(6)}) == ([None] * 6, {})
    # A "speaker" with very little speech (a cough) joins the nearest real one.
    tiny = [(0.0, 20.0), (20.0, 40.0), (40.0, 42.0)]
    assert speakers.label(tiny, {0: _voice(1), 1: _voice(1), 2: _voice(3)})[0] == [None, None, None]


def test_voices_are_remembered_recognized_and_follow_the_dictionary():
    v = list(_voice(5))
    dictionary.update(lambda d: d.add(dictionary.PEOPLE, "Lucía"))
    dictionary.remember_voice("Lucía", v)
    assert dictionary.recognize(list(_voice(5)), speakers.similarity, speakers.RECOGNIZE) == "Lucía"
    assert dictionary.recognize(list(_voice(6)), speakers.similarity, speakers.RECOGNIZE) is None
    dictionary.remember_voice("Lucía", v)
    assert dictionary.voices()["Lucía"]["recordings"] == 2
    dictionary.update(lambda d: (d.add(dictionary.PEOPLE, "Lucía Fernández"), d.merge("Lucía", "Lucía Fernández")))
    assert "Lucía Fernández" in dictionary.voices() and "Lucía" not in dictionary.voices()
    dictionary.update(lambda d: d.remove("Lucía Fernández"))
    assert dictionary.voices() == {}


class VoiceEngine(StubEngine):
    labels_speakers = True


def test_worker_labels_speakers_and_suggests_known_voices(tmp_path, monkeypatch):
    lib_ = Library(tmp_path / "data")
    pattern = []
    for _ in range(4):
        pattern += [(15, True), (3, False)]
    rec = importer.import_file(lib_, speechy_wav(tmp_path / "c.wav", pattern)).recording
    # Passages alternate between two voices; the second voice is someone the user named before.
    dictionary.remember_voice("Ana", list(_voice(2)))
    calls = []

    class FakeEmbedder:
        @staticmethod
        def available():
            return True

        def embed(self, samples):
            calls.append(len(samples))
            return _voice(1 if len(calls) % 2 else 2)

    monkeypatch.setattr(speakers, "Embedder", FakeEmbedder)
    rec.request_transcription()
    from echo_app.worker.service import Worker

    Worker(lib_, VoiceEngine()).process(rec)
    t = rec.transcript()
    assert [s["speaker"] for s in t["segments"]] == [1, 2, 1, 2]
    assert all(s["paragraph"] for s in t["segments"])  # each turn is a paragraph
    assert t["speakers"]["count"] == 2 and t["speakers"]["suggested"] == {"2": "Ana"}
    assert len(t["speakers"]["centroids"]["1"]) == 256
    # A monologue recording is not labeled.
    rec.update(speakers_off=True)
    rec.request_transcription()
    Worker(lib_, VoiceEngine()).process(rec)
    assert "speakers" not in rec.transcript()


def _with_speakers(lib_, tmp_path):
    rec = _transcribed(lib_, tmp_path)
    t = json.loads(rec.path("transcript.json").read_text())
    t["segments"][0]["speaker"], t["segments"][1]["speaker"] = 1, 2
    t["speakers"] = {"count": 2, "centroids": {"1": list(_voice(1)), "2": list(_voice(2))}, "suggested": {}}
    rec.path("transcript.json").write_text(json.dumps(t))
    return rec


def test_exports_carry_the_names(lib, tmp_path):
    rec = _with_speakers(lib, tmp_path)
    rec.update(speakers={"1": "Ana"})
    assert export.render_transcript(rec, ".txt") == "Ana: Hola mundo.\n\nSpeaker 2: Segunda parte.\n"
    assert "<v Ana>Hola mundo." in export.render_transcript(rec, ".vtt")
    assert "Speaker 2: Segunda parte." in export.render_transcript(rec, ".srt")
    assert json.loads(export.render_transcript(rec, ".json"))["segments"][0]["speaker"] == "Ana"
    assert "**Ana:** Hola mundo." in export.to_markdown(rec)
    rec.update(speakers_off=True)
    assert export.render_transcript(rec, ".txt") == "Hola mundo.\n\nSegunda parte.\n"


def test_naming_in_the_editor(window, lib, tmp_path):
    rec = _with_speakers(lib, tmp_path)
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    labels = tp.editor.margin.labels
    assert [(t, n) for _p, t, _c, n in labels] == [("Speaker 1", 1), ("Speaker 2", 2)]
    assert "2 speakers" in tp.status.text()
    tp.name_speaker(1, "Ana López")
    assert lib.get(rec.id).meta.speakers == {"1": "Ana López"}
    assert dictionary.load().find("Ana López").kind == dictionary.PEOPLE
    assert "Ana López" in dictionary.voices()
    assert tp.editor.margin.labels[0][1] == "Ana López"
    tp.set_speakers_off(True)
    assert lib.get(rec.id).meta.speakers_off and not tp.editor.margin.labels
    tp.editor.margin.grab()


def test_label_per_track_keeps_sides_apart_and_mic_first():
    passages = [(i * 10.0, i * 10.0 + 9) for i in range(5)]
    embs = {0: _voice(1), 1: _voice(1), 3: _voice(1), 4: _voice(1)}  # one voice; passage 2 is short
    sides = [1, 0, 1, 1, 0]
    labels, centroids = speakers.label(passages, embs, tracks=sides)
    assert labels == [2, 1, 2, 2, 1] and set(centroids) == {1, 2}
    assert speakers.label(passages, embs) == ([None] * 5, {})  # without tracks: one speaker


def test_louder_track():
    rate = 1000
    stereo = np.zeros((4000, 2), np.int16)
    stereo[:2000, 0] = 8000
    stereo[:2000, 1] = 500  # the call faintly in the room's microphone would look like this
    stereo[2000:, 1] = 6000
    assert speakers.louder_track(stereo, [(0, 2), (2, 4), (5, 6)], rate) == [0, 1, 0]


def _call(lib_, tmp_path, sides=(1, 0, 1, 0)):
    """A call recording: 15 s passages, each on the microphone (0) or the computer audio (1)."""
    import subprocess

    n, gap = 15 * 16000, np.zeros((3 * 16000, 2), np.int16)
    tone = (np.sin(np.arange(n) * 0.1) * 8000).astype(np.int16)
    parts = []
    for side in sides:
        p = np.zeros((n, 2), np.int16)
        p[:, side] = tone
        parts += [p, gap]
    path = tmp_path / "call.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", "16000", "-ac", "2", "-i", "pipe:0",
                    str(path)], input=np.concatenate(parts).tobytes(), check=True)
    rec = importer.import_file(lib_, path).recording
    rec.update(tracks=["mic", "computer"])
    return rec


def _embedder(monkeypatch, voices):
    """Embeddings in turn from `voices` (seeds), repeating."""
    calls = []

    class Embedder:
        @staticmethod
        def available():
            return True

        def embed(self, samples):
            calls.append(1)
            return _voice(voices[(len(calls) - 1) % len(voices)])

    monkeypatch.setattr(speakers, "Embedder", Embedder)


def _process(lib_, rec):
    from echo_app.worker.service import Worker

    rec.request_transcription()
    Worker(lib_, VoiceEngine()).process(rec)
    return rec.reload().transcript()


def test_worker_labels_a_call_by_track(tmp_path, monkeypatch):
    """Two people with indistinguishable voices: the tracks alone tell the user from the call."""
    lib_ = Library(tmp_path / "data")
    rec = _call(lib_, tmp_path)  # the call speaks first
    _embedder(monkeypatch, [1])
    t = _process(lib_, rec)
    assert [s["speaker"] for s in t["segments"]] == [2, 1, 2, 1]
    assert t["speakers"]["count"] == 2 and t["speakers"]["tracks"] == {"1": 0, "2": 1}
    assert "me" not in t["speakers"] and rec.meta.speakers == {}  # nobody's name is known


def test_call_names_the_user_and_learns_their_voice(tmp_path, monkeypatch):
    from echo_app import settings

    settings.save(settings.Settings(your_name="Sofía"))
    lib_ = Library(tmp_path / "data")
    rec = _call(lib_, tmp_path)
    _embedder(monkeypatch, [2, 1])  # the call is voice 2, the user voice 1
    t = _process(lib_, rec)
    assert t["speakers"]["me"] == 1 and rec.meta.speakers == {"1": "Sofía"}
    assert speakers.similarity(dictionary.voices()["Sofía"]["voice"], _voice(1)) > 0.95


def test_recognized_voice_names_the_user_without_learning_from_it(tmp_path, monkeypatch):
    from echo_app import settings

    settings.save(settings.Settings(your_name="Sofía"))
    dictionary.remember_voice("Sofía", list(_voice(1)))
    lib_ = Library(tmp_path / "data")
    pattern = []
    for _ in range(4):
        pattern += [(15, True), (3, False)]
    rec = importer.import_file(lib_, speechy_wav(tmp_path / "m.wav", pattern)).recording
    _embedder(monkeypatch, [3, 1])  # someone else first, then the user
    t = _process(lib_, rec)
    assert t["speakers"]["me"] == 2 and rec.meta.speakers == {"2": "Sofía"}
    assert dictionary.voices()["Sofía"]["recordings"] == 1  # a match is not folded back in


def test_the_users_names_are_never_replaced(tmp_path, monkeypatch):
    from echo_app import settings

    lib_ = Library(tmp_path / "data")
    rec = _call(lib_, tmp_path)
    _embedder(monkeypatch, [2, 1])
    rec.update(speakers={"1": "Lucía"})  # someone else on the user's microphone, named by the user
    settings.save(settings.Settings(your_name="Sofía"))
    t = _process(lib_, rec)
    assert "me" not in t["speakers"] and rec.meta.speakers == {"1": "Lucía"}
    rec.update(speakers={})
    settings.save(settings.Settings(your_name=""))
    t = _process(lib_, rec)
    assert "me" not in t["speakers"] and rec.meta.speakers == {}  # no name set: nobody is named

"""Real-model smoke test. Opt-in: ECHO_MODEL_TESTS=1 (needs the GPU profile and downloaded models)."""

import os
import shutil
import subprocess

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("ECHO_MODEL_TESTS") != "1" or not shutil.which("espeak-ng"),
                                reason="set ECHO_MODEL_TESTS=1 (and install espeak-ng) to run the real model")

SENTENCE = ("Hola, me llamo Mauro y estoy probando la transcripción. "
            "Mañana tengo una reunión con el equipo de Surus.")


def speech(tmp_path):
    wav = tmp_path / "s.wav"
    subprocess.run(["espeak-ng", "-v", "es", "-s", "150", "-w", str(wav), SENTENCE], check=True)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(wav), "-f", "s16le", "-ac", "1", "-ar", "16000",
                          "pipe:1"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16)


def test_engine_transcribes_spanish(tmp_path, real_models):
    from echo_app.worker.asr import Engine

    e = Engine()
    clip = speech(tmp_path)
    with_adapter = e.transcribe([clip], adapter=True)[0]
    base = e.transcribe([clip], adapter=False)[0]
    for text in (with_adapter, base):
        assert "Mauro" in text and "reunión" in text and text.endswith(".")
    # Known terms in the context slot fix spellings the model would otherwise guess.
    assert "Surus" in e.transcribe([clip], context="En esta conversación se mencionan Surus y Mauro.")[0]
    regions = e.speech_regions(np.concatenate([np.zeros(16000 * 2, np.int16), clip, np.zeros(16000 * 2, np.int16)]))
    assert len(regions) >= 1 and regions[0][0] >= 1.5


def test_short_output_is_retried(tmp_path, real_models, monkeypatch):
    from echo_app.worker import asr

    e = asr.Engine()
    clip = speech(tmp_path)
    # A context known to make the model return nothing on this clip must not lose the speech.
    monkeypatch.setattr(asr, "build_context", lambda extra: asr.STYLE_CONTEXT + " Términos: Surus, Mauro.")
    text = e.transcribe([clip], context="x")[0]
    assert "Mauro" in text and len(text.split()) >= asr.min_words(len(clip) / 16000)


def test_dictionary_sentence_does_not_drop_speech(tmp_path, real_models):
    from echo_app import dictionary
    from echo_app.worker.asr import Engine

    e = Engine()
    clip = speech(tmp_path)
    plain = e.transcribe([clip])[0]
    d = dictionary.Dictionary()
    for name in ("Lucía Fernández", "Mauro", "Surus", "PipeWire", "Joaquín Ibarra", "Valparaíso", "Cohere",
                 "Marta Ruiz", "Tandil", "Kubernetes"):
        d.add(dictionary.kind_of(name), name)
    sentence, names = dictionary.context_sentence(d)
    assert len(names) == 10
    with_names = e.transcribe([clip], context=sentence)[0]
    assert len(with_names.split()) >= len(plain.split())
    # Spelling is not asserted: with ten names in the sentence the model still wrote "Zurus" on
    # this clip (2026-10-24), while two names fix it (above). The corrector covers the rest.
    assert "Mauro" in with_names

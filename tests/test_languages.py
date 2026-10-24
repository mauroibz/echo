"""A language per recording: the list offered, the request, the worker and the adapter rule."""

import importlib.util
import json

import pytest

from echo_app import models, settings, transcription
from echo_app.library import REQUESTED, Library
from echo_app.worker import asr


@pytest.mark.skipif(importlib.util.find_spec("transformers") is None, reason="needs a transcription profile")
def test_language_list_matches_the_installed_processor():
    from transformers.models.cohere_asr import processing_cohere_asr

    assert set(models.PROCESSOR_LANGUAGES) == set(processing_cohere_asr.LANGUAGES)


def test_supported_languages_put_spanish_first():
    langs = models.supported_languages()
    assert langs[0] == "es" and "en" in langs and set(langs) <= set(models.PROCESSOR_LANGUAGES)
    assert models.language_name("en") == "English" and models.language_name("xx") == "xx"


def test_style_sentence_and_context_per_language():
    assert asr.build_context(None, "es") == asr.STYLE_CONTEXTS["es"]
    assert asr.build_context("Términos: Surus.", "en") == "Términos: Surus. " + asr.STYLE_CONTEXTS["en"]
    assert asr.build_context(None, "de") is None  # no style sentence: no context at all
    assert asr.build_context("Personen: Ana.", "de") == "Personen: Ana."
    assert asr.word_count("明天早上我要去办公室", "zh") == 5 and asr.word_count("dos palabras", "es") == 2


def test_request_carries_the_language(tmp_path):
    lib = Library(tmp_path / "data")
    rec = lib.create("t", "imported")
    transcription.request(lib, rec)
    assert json.loads(rec.path(REQUESTED).read_text())["language"] == "es"
    settings.save(settings.Settings(language="pt"))
    transcription.request(lib, rec)
    assert json.loads(rec.path(REQUESTED).read_text())["language"] == "pt"
    rec.update(language="en")
    transcription.request(lib, rec)
    assert json.loads(rec.path(REQUESTED).read_text())["language"] == "en"


def test_worker_uses_the_language_and_drops_the_adapter(tmp_path):
    from echo_app import importer
    from test_worker import StubEngine, speechy_wav
    from echo_app.worker.service import Worker

    lib = Library(tmp_path / "data")
    rec = importer.import_file(lib, speechy_wav(tmp_path / "a.wav", [(1, False), (5, True), (1, False)])).recording
    rec.update(language="en")
    transcription.request(lib, rec, adapter=True)
    eng = StubEngine()
    Worker(lib, eng).process(rec)
    t = rec.transcript()
    assert eng.languages == ["en"]
    assert t["language"] == "en" and t["model"]["adapter_enabled"] is False and t["model"]["adapter"] is None


def test_cli_language_flag(tmp_path, monkeypatch):
    from echo_app import cli, features

    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    rec = Library(tmp_path / "data").create("t", "imported", audio="a.wav", sha256="x")
    monkeypatch.setattr(features, "transcription_installed", lambda: True)
    monkeypatch.setattr(models, "all_cached", lambda: True)
    assert cli.main(["transcribe", rec.id, "--language", "fr"]) == 0
    assert json.loads(rec.path(REQUESTED).read_text())["language"] == "fr"
    assert Library(tmp_path / "data").get(rec.id).meta.language == "fr"

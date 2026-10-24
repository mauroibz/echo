"""Aligning edited text to passages, and the timed exports built on it."""

import json

from echo_app import align, export
from echo_app.library import Library
from echo_app.worker.planning import join_text

SEGS = [{"start": 0.0, "end": 2.0, "text": "Hola mundo.", "paragraph": True},
        {"start": 2.5, "end": 4.25, "text": "Esto es una prueba.", "paragraph": False},
        {"start": 3725.0, "end": 3730.5, "text": "Segunda parte aquí.", "paragraph": True}]


def pieces(text):
    return [(k, text[s:e]) for s, e, k in align.align(SEGS, text)]


def test_unedited_text_maps_exactly():
    text = join_text(SEGS)
    assert pieces(text) == [(0, "Hola mundo."), (1, "Esto es una prueba."), (2, "Segunda parte aquí.")]


def test_edited_words_keep_their_passage():
    text = "Hola Mundo querido. Esto fue una prueba.\n\nParte dos aquí, editada."
    assert pieces(text) == [(0, "Hola Mundo querido."), (1, "Esto fue una prueba."),
                            (2, "Parte dos aquí, editada.")]


def test_deleted_passage_is_empty_and_added_intro_joins_the_first():
    assert pieces("Hola mundo.\n\nSegunda parte aquí.") == [(0, "Hola mundo."), (1, ""), (2, "Segunda parte aquí.")]
    assert pieces("Intro nueva. Hola mundo. Esto es una prueba.\n\nSegunda parte aquí.")[0] == \
        (0, "Intro nueva. Hola mundo.")


def test_accents_and_case_do_not_break_the_alignment():
    assert pieces("HOLA MUNDO. Ésto es una prueba.\n\nSegunda parte aqui.")[1] == (1, "Ésto es una prueba.")


def test_moved_sentence_does_not_reorder_passages():
    text = "Segunda parte aquí. Hola mundo. Esto es una prueba."
    spans = align.align(SEGS, text)
    starts = [s for s, e, _k in spans if e > s]
    assert starts == sorted(starts)


def _rec(tmp_path, edited=None):
    lib = Library(tmp_path / "data")
    rec = lib.create("Charla", "imported", duration=3731.0)
    rec.path("transcript.json").write_text(json.dumps({"segments": SEGS, "text": join_text(SEGS),
                                                       "created": "2026-10-24T10:00:00", "language": "es"}))
    if edited:
        rec.save_edited(edited)
    return rec


def test_srt_and_vtt(tmp_path):
    rec = _rec(tmp_path, "Hola mundo. Esto fue una prueba.\n\nSegunda parte aquí.")
    srt = export.render_transcript(rec, ".srt")
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,000\nHola mundo.\n\n2\n00:00:02,500 --> 00:00:04,250\n"
                          "Esto fue una prueba.\n")
    assert "3\n01:02:05,000 --> 01:02:10,500\nSegunda parte aquí.\n" in srt
    vtt = export.render_transcript(rec, ".vtt")
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHola mundo.\n")


def test_json_export(tmp_path):
    rec = _rec(tmp_path)
    data = json.loads(export.render_transcript(rec, ".json"))
    assert data["title"] == "Charla" and data["language"] == "es" and data["edited"] is False
    assert data["segments"][2] == {"start": 3725.0, "end": 3730.5, "text": "Segunda parte aquí.", "paragraph": True}


def test_copy_with_timestamps(tmp_path):
    rec = _rec(tmp_path)
    assert export.with_timestamps(rec) == ("[0:00] Hola mundo.\n[0:02] Esto es una prueba.\n\n"
                                           "[1:02:05] Segunda parte aquí.\n")


def test_export_dispatches_on_suffix(tmp_path):
    rec = _rec(tmp_path)
    out = export.export_transcript(rec, tmp_path / "x.srt")
    assert out.suffix == ".srt" and out.read_text().startswith("1\n")
    out = export.export_transcript(rec, tmp_path / "x.weird")
    assert out.suffix == ".txt"


def test_cli_export(tmp_path, capsys):
    from echo_app import cli, settings

    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    rec = _rec(tmp_path)
    assert cli.main(["export", rec.id, "--format", "vtt"]) == 0
    assert capsys.readouterr().out.startswith("WEBVTT")
    assert cli.main(["export", rec.id, "--out", str(tmp_path / "subs.srt")]) == 0
    assert (tmp_path / "subs.srt").read_text().startswith("1\n00:00:00,000")
    assert cli.main(["export", "nope"]) == 1


def test_words_added_after_a_paragraph_break_join_the_next_passage():
    assert pieces("Hola mundo. Esto es una prueba.\n\nY ahora la segunda parte aquí.")[2] == \
        (2, "Y ahora la segunda parte aquí.")

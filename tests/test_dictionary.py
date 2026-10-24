"""The dictionary: store, context sentence, learning from edits and titles, the corrector."""

import json
import sys

import pytest

from echo_app import dictionary as D
from echo_app import transcription
from echo_app.library import CORRECTED, EDITED, REQUESTED, TRANSCRIPT, Library
from echo_app.worker import planning


def make(*entries, muted=()):
    d = D.Dictionary(muted=list(muted))
    for kind, name, aliases, used in entries:
        d.add(kind, name, aliases).used = used
    return d


# ---- store --------------------------------------------------------------------------------------

def test_round_trip_and_hand_edits(tmp_path):
    path = tmp_path / "glossary.toml"
    d = make((D.PEOPLE, "Lucía Fernández", ["Lucia Fernandez"], "2026-10-24T10:00:00+02:00"),
             (D.TERMS, 'Surus "AI"', ["zurus"], ""), muted=["Cosa"])
    d.save(path)
    again = D.load(path)
    assert [(e.kind, e.name, e.aliases, e.used) for e in again.entries] == \
        [(D.PEOPLE, "Lucía Fernández", ["Lucia Fernandez"], "2026-10-24T10:00:00+02:00"),
         (D.TERMS, 'Surus "AI"', ["zurus"], "")]
    assert again.muted == ["Cosa"]
    # A hand-added entry with only a name is read.
    path.write_text(path.read_text() + '\n[[terms]]\nname = "PipeWire"\n', encoding="utf-8")
    assert D.load(path).find("pipewire").name == "PipeWire"


def test_a_broken_file_is_never_saved_over(tmp_path, monkeypatch):
    path = D.dictionary_path()
    D.update(lambda d: d.add(D.TERMS, "Surus"))
    assert D.current().find("Surus")
    good = path.read_text()
    path.write_text(good + "\n[[people]\nname = ", encoding="utf-8")  # mid-save, or a typo
    assert D.current().find("Surus")  # the last good copy is still used
    with pytest.raises(D.Unreadable):
        D.update(lambda d: d.add(D.TERMS, "Otro"))
    assert path.read_text().startswith(good)  # untouched, nothing moved aside
    assert not list(path.parent.glob("*.bad"))


def test_add_merges_aliases_and_merge_keeps_both():
    d = make((D.PEOPLE, "Lucía Fernández", [], ""))
    d.add(D.PEOPLE, "lucía fernández", ["Lucia"])  # same name, folded
    assert len(d.entries) == 1 and d.entries[0].aliases == ["Lucia"]
    d.add(D.PEOPLE, "Lucia F.", ["Luci"])
    kept = d.merge("Lucia F.", "Lucía Fernández")
    assert [e.name for e in d.entries] == ["Lucía Fernández"]
    assert kept.aliases == ["Lucia", "Lucia F.", "Luci"]
    assert d.knows("luci") and d.remove("Lucía Fernández") and not d.entries


def test_mute_and_knows():
    d = D.Dictionary()
    d.mute("Cosa")
    d.mute("cosa")
    assert d.muted == ["Cosa"] and d.knows("COSA")


# ---- context sentence -------------------------------------------------------------------------

def test_context_sentence_order_and_line():
    d = make((D.TERMS, "Surus", [], "2026-10-20"), (D.PEOPLE, "Mauro", [], "2026-10-01"),
             (D.PEOPLE, "Lucía Fernández", [], "2026-10-24"), (D.TERMS, "PipeWire", [], "2026-10-23"))
    text, names = D.context_sentence(d, "Entrevista con Lucía sobre PipeWire")
    assert text == ("Entrevista con Lucía sobre PipeWire. Personas: Lucía Fernández, Mauro. "
                    "Términos: PipeWire, Surus.")
    assert names == ["Lucía Fernández", "Mauro", "PipeWire", "Surus"]
    assert D.context_sentence(D.Dictionary(), "") == ("", [])
    assert D.context_sentence(D.Dictionary(), "Charla con Ana!")[0] == "Charla con Ana!"


def test_context_budget_cuts_whole_entries_least_recent_first():
    d = make(*[(D.TERMS, f"Termino{i:02d}", [], f"2026-10-{i + 1:02d}") for i in range(30)])
    text, names = D.context_sentence(d, budget=40)
    assert names and len(names) < 30
    assert names[0] == "Termino29"  # most recent first
    assert all(n in text for n in names) and "Termino00" not in text
    assert len(text) // D.CHARS_PER_TOKEN <= 40


# ---- learning ----------------------------------------------------------------------------------

def test_capitalized_replacement_is_a_candidate():
    c = D.edit_candidates("Mañana voy a zurus con el equipo.", "Mañana voy a Surus con el equipo.", D.Dictionary(),
                          "r1")
    assert c == [D.Candidate(D.TERMS, "Surus", "zurus")]


def test_case_change_alone_counts_for_names_not_common_words():
    model = "hablé con mauro. como estás"
    edited = "hablé con Mauro. Cómo estás"
    assert D.edit_candidates(model, edited, D.Dictionary(), "r1") == [D.Candidate(D.TERMS, "Mauro", "mauro")]


def test_two_word_name_is_a_person():
    c = D.edit_candidates("vino lucia fernandes ayer", "vino Lucía Fernández ayer", D.Dictionary(), "r1")
    assert c == [D.Candidate(D.PEOPLE, "Lucía Fernández", "lucia fernandes")]


def test_sentence_start_capital_is_not_enough():
    assert D.edit_candidates("Hola. zurus vino.", "Hola. Surus vino.", D.Dictionary(), "r1") == []


def test_lower_case_replacement_needs_two_recordings():
    model, edited = "uso pipe wire en casa", "uso pipewire en casa"
    assert D.edit_candidates(model, edited, D.Dictionary(), "rec-a") == []
    assert D.edit_candidates(model, edited, D.Dictionary(), "rec-a") == []  # same recording again
    assert D.edit_candidates(model, edited, D.Dictionary(), "rec-b") == [D.Candidate(D.TERMS, "pipewire", "pipe wire")]


def test_known_and_muted_words_are_not_offered():
    d = make((D.TERMS, "Surus", [], ""), muted=["Pepe"])
    assert D.edit_candidates("vi a zurus y a pepe", "vi a Surus y a Pepe", d, "r1") == []


def test_long_rewrites_are_not_candidates():
    assert D.edit_candidates("esto no se entiende nada bien", "Esto Lo Reescribí Entero Ahora Mismo", D.Dictionary(),
                             "r1") == []


def test_new_spelling_of_a_known_name_becomes_an_alias():
    d = make((D.TERMS, "Villaamil", ["villalmil"], ""))
    model, edited = "dijo Villamil a la casa", "dijo Villaamil a la casa"
    assert D.edit_candidates(model, edited, d, "r1") == []  # known: no chip
    assert D.new_aliases(model, edited, d) == [("Villaamil", "Villamil")]
    assert D.new_aliases("dijo villalmil", "dijo Villaamil", d) == []  # already an alias


def test_title_candidates():
    c = D.title_candidates("Entrevista con Lucía Fernández sobre PipeWire", "Hola a todos", D.Dictionary())
    assert c == [D.Candidate(D.PEOPLE, "Lucía Fernández"), D.Candidate(D.TERMS, "PipeWire")]
    assert D.title_candidates("Recording 2026-10-24 03:39", "", D.Dictionary()) == []
    # Words already in the first sentence were spelled by the model; nothing to learn.
    assert D.title_candidates("Charla Surus", "Hoy en Surus hablamos.", D.Dictionary()) == []


# ---- corrector ---------------------------------------------------------------------------------

def test_aliases_and_fuzzy_names_are_corrected_with_a_log():
    d = make((D.TERMS, "Surus", ["zurus"], ""), (D.PEOPLE, "Lucía Fernández", [], ""))
    text, edits = D.correct_segment("Hablé con lucia fernandes y con Zurus.", d)
    assert text == "Hablé con Lucía Fernández y con Surus."
    assert [(e["before"], e["after"]) for e in edits] == [("lucia fernandes", "Lucía Fernández"), ("Zurus", "Surus")]
    for e in edits:
        assert text[e["start"]:e["end"]] == e["after"]


def test_common_single_words_are_never_corrected():
    d = make((D.PEOPLE, "Luz", ["luz"], ""), (D.TERMS, "Casa", ["casa"], ""))
    assert D.correct_segment("la luz de la casa", d) == ("la luz de la casa", [])


def test_whole_tokens_only():
    d = make((D.TERMS, "Surus", ["zurus"], ""))
    assert D.correct_segment("zurusito y azurus", d)[1] == []


def test_rejected_spot_is_left_alone():
    d = make((D.TERMS, "Surus", ["zurus"], ""))
    text, edits = D.correct_segment("zurus y zurus", d, {(8, "zurus")})
    assert text == "Surus y zurus" and len(edits) == 1


def _transcribed(lib, tmp_path, texts):
    rec = lib.create("t", "imported")
    segs = [{"start": i * 10.0, "end": i * 10.0 + 8, "text": t, "paragraph": i == 0} for i, t in enumerate(texts)]
    (rec.folder / TRANSCRIPT).write_text(json.dumps({"created": "2026-10-24T10:00:00", "segments": segs,
                                                      "text": planning.join_text(segs)}), encoding="utf-8")
    return rec


def test_apply_writes_a_copy_and_text_prefers_it(tmp_path):
    lib = Library(tmp_path / "data")
    rec = _transcribed(lib, tmp_path, ["Hoy con zurus.", "Luego más zurus."])
    model = rec.model_text()
    d = make((D.TERMS, "Surus", ["zurus"], ""))
    assert D.apply(rec, d)
    assert rec.model_text() == model  # the model output is never changed
    assert rec.text() == "Hoy con Surus. Luego más Surus."
    assert not D.apply(rec, d)  # up to date
    # A new alias reaches an existing transcript without re-transcribing.
    d.add(D.TERMS, "Hoy", [])  # common single word: no effect
    D.apply(rec, d)
    assert rec.text() == "Hoy con Surus. Luego más Surus."
    # Undo one spot; it stays undone when the corrector runs again.
    first = rec.corrected()["edits"][0]
    D.Dictionary.save(d, D.dictionary_path())
    D.undo(rec, first)
    assert rec.text() == "Hoy con zurus. Luego más Surus."
    d.add(D.TERMS, "Mauro", [])
    D.apply(rec, d)
    assert rec.text() == "Hoy con zurus. Luego más Surus."


def test_corrector_never_touches_edited_text(tmp_path):
    lib = Library(tmp_path / "data")
    rec = _transcribed(lib, tmp_path, ["con zurus"])
    rec.save_edited("con zurus, editado")
    assert not D.apply(rec, make((D.TERMS, "Surus", ["zurus"], "")))
    assert not rec.path(CORRECTED).exists() and rec.text() == "con zurus, editado"


def test_stale_copy_from_an_earlier_run_is_ignored(tmp_path):
    lib = Library(tmp_path / "data")
    rec = _transcribed(lib, tmp_path, ["con zurus"])
    D.apply(rec, make((D.TERMS, "Surus", ["zurus"], "")))
    t = json.loads((rec.folder / TRANSCRIPT).read_text())
    t["created"] = "2026-10-25T10:00:00"
    (rec.folder / TRANSCRIPT).write_text(json.dumps(t))
    assert rec.corrected() is None and rec.text() == "con zurus"


# ---- requests ------------------------------------------------------------------------------------

def test_request_carries_the_context_and_touches_entries(tmp_path):
    lib = Library(tmp_path / "data")
    rec = lib.create("t", "imported")
    rec.update(context_line="Entrevista con Lucía")
    D.update(lambda d: d.add(D.TERMS, "Surus", ["zurus"]))
    transcription.request(lib, rec, adapter=True)
    req = json.loads(rec.path(REQUESTED).read_text())
    assert req["context"] == "Entrevista con Lucía. Términos: Surus."
    assert D.load().find("Surus").used
    # The CLI's --context replaces the line for one run.
    transcription.request(lib, rec, adapter=True, context="Charla técnica")
    assert json.loads(rec.path(REQUESTED).read_text())["context"] == "Charla técnica. Términos: Surus."


def test_request_without_context_has_no_key(tmp_path):
    lib = Library(tmp_path / "data")
    rec = lib.create("t", "imported")
    transcription.request(lib, rec, adapter=False)
    assert "context" not in json.loads(rec.path(REQUESTED).read_text())


def test_cli_context_flag(tmp_path, monkeypatch, capsys):
    from echo_app import cli, features, settings

    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    lib = Library(tmp_path / "data")
    rec = lib.create("t", "imported", audio="audio.wav", sha256="x")
    monkeypatch.setattr(features, "transcription_installed", lambda: True)
    assert cli.main(["transcribe", rec.id, "--context", "Charla con Ana"]) == 0
    assert json.loads(rec.path(REQUESTED).read_text())["context"] == "Charla con Ana."

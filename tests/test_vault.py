"""Markdown notes for a vault: content, folder export, the command line and sync."""

import json

from echo_app import cli, dictionary, export, settings
from echo_app.library import Library
from echo_app.worker.planning import join_text
from test_ui import lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures

SEGS = [{"start": 0.0, "end": 5.0, "text": "Hola, soy Lucía.", "paragraph": True},
        {"start": 6.0, "end": 9.0, "text": "Hablemos del precio.", "paragraph": True},
        {"start": 65.0, "end": 70.0, "text": "Y ahora el cierre.", "paragraph": True}]


def _rec(library, title="Charla con Lucía"):
    rec = library.create(title, "imported", duration=72.0)
    rec.update(created="2026-10-24T10:30:00-03:00")
    (rec.folder / "audio.opus").write_bytes(b"opus")
    rec.update(audio="audio.opus")
    rec.path("transcript.json").write_text(json.dumps({"segments": SEGS, "text": join_text(SEGS),
                                                       "created": "2026-10-24T11:00:00"}))
    return rec


def test_note_content(tmp_path):
    library = Library(tmp_path / "data")
    rec = _rec(library)
    rec.set_tags(["entrevista", "mi proyecto"])
    rec.update(notes="Primera charla.")
    rec.set_markers([{"at": 6.5, "note": "precio"}, {"at": 66.0, "note": ""}])
    dictionary.update(lambda d: d.add(dictionary.PEOPLE, "Lucía Fernández", ["Lucía"]))
    note = export.to_markdown(rec, timestamps=True, audio_link="../data/audio.opus")
    assert note.startswith("# Charla con Lucía\n\n_2026-10-24 10:30_ · 1:12 · #entrevista #mi-proyecto\n")
    assert "People: Lucía Fernández" in note
    assert "Audio: [audio.opus](<../data/audio.opus>)" in note and "> Primera charla." in note
    body = note.split("> Primera charla.\n\n")[1]
    assert body == ("## 0:00 Inicio\n\n[0:00] Hola, soy Lucía.\n\n## 0:06 precio\n\n[0:06] Hablemos del precio.\n\n"
                    "## 1:06\n\n[1:05] Y ahora el cierre.\n")


def test_without_markers_no_headings(tmp_path):
    rec = _rec(Library(tmp_path / "data"))
    note = export.to_markdown(rec)
    assert "##" not in note and note.endswith("Hola, soy Lucía.\n\nHablemos del precio.\n\nY ahora el cierre.\n")


def test_folder_export_skips_up_to_date_and_follows_renames(tmp_path):
    library = Library(tmp_path / "data")
    rec = _rec(library)
    vault = tmp_path / "vault"
    assert export.export_folder([rec], vault)["written"] == 1
    note = vault / "2026-10-24 Charla con Lucía.md"
    assert note.exists() and "Audio: [audio.opus](<../data/recordings/" in note.read_text()
    assert export.export_folder([rec], vault) == {"written": 0, "unchanged": 1, "removed": 0, "kept": 0}
    rec.update(title="Entrevista Lucía")
    counts = export.export_folder([library.get(rec.id)], vault)
    assert counts["written"] == 1 and counts["removed"] == 1
    assert not note.exists() and (vault / "2026-10-24 Entrevista Lucía.md").exists()
    # Copying the audio puts it next to the notes.
    export.export_folder([library.get(rec.id)], vault, audio=export.AUDIO_COPY)
    assert (vault / "audio" / f"{rec.id}.opus").read_bytes() == b"opus"


def test_same_titles_get_distinct_files(tmp_path):
    library = Library(tmp_path / "data")
    a, b = _rec(library, "Diario"), _rec(library, "Diario")
    export.export_folder([a, b], tmp_path / "v")
    assert sorted(p.name for p in (tmp_path / "v").glob("*.md")) == ["2026-10-24 Diario 2.md", "2026-10-24 Diario.md"]


def test_cli_export_all(tmp_path, capsys):
    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    _rec(Library(tmp_path / "data"))
    assert cli.main(["export", "--all", str(tmp_path / "vault"), "--timestamps", "--audio", "none"]) == 0
    assert "1 written" in capsys.readouterr().out
    note = next((tmp_path / "vault").glob("*.md")).read_text()
    assert "[0:00] Hola" in note and "Audio:" not in note


def test_window_keeps_the_folder_up_to_date(window, lib, tmp_path):
    vault = tmp_path / "vault"
    cfg, _ = settings.load()
    cfg.export_dir, cfg.export_sync = str(vault), True
    settings.save(cfg)
    rec = _rec(lib)
    window._sync_timer.setInterval(200)
    window._refresh()
    rec.update(title="Renombrada")
    window._refresh()
    assert wait_until(lambda: (vault / "2026-10-24 Renombrada.md").exists(), 10)


def test_never_overwrites_files_it_did_not_write_or_the_user_changed(tmp_path):
    library = Library(tmp_path / "data")
    rec = _rec(library)
    vault = tmp_path / "vault"
    vault.mkdir()
    mine = vault / "2026-10-24 Charla con Lucía.md"
    mine.write_text("my own note")  # already there, not Echo's
    export.export_folder([rec], vault)
    assert mine.read_text() == "my own note" and (vault / "2026-10-24 Charla con Lucía 2.md").exists()
    # The user edits Echo's note: it is left alone from then on, also when the recording is renamed.
    ours = vault / "2026-10-24 Charla con Lucía 2.md"
    ours.write_text(ours.read_text() + "\nmis apuntes\n")
    rec.update(title="Otra")
    counts = export.export_folder([library.get(rec.id)], vault)
    assert counts["kept"] == 1 and ours.read_text().endswith("mis apuntes\n")
    assert not (vault / "2026-10-24 Otra.md").exists()

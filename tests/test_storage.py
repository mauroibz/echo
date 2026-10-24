import json
import os
from pathlib import Path

import pytest

from echo_app import fsutil, library, paths, settings
from echo_app.index import Index
from echo_app.library import Library


def test_default_data_dir(isolated_home):
    assert paths.default_data_dir() == isolated_home / ".local/share/echo"


def test_settings_defaults_and_roundtrip(isolated_home):
    s, warn = settings.load()
    assert warn is None and s.sample_rate == 48000 and s.data_path == paths.default_data_dir()
    s.source = 'weird "name"'
    s.use_adapter = False
    settings.save(s)
    s2, _ = settings.load()
    assert s2.source == 'weird "name"' and s2.use_adapter is False


def test_settings_unknown_and_wrong_type_ignored(isolated_home):
    p = settings.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text('sample_rate = "fast"\nunknown_key = 3\nchannels = 2\n')
    s, warn = settings.load()
    assert warn is None and s.sample_rate == 48000 and s.channels == 2


def test_settings_corrupt_file_backed_up(isolated_home):
    p = settings.settings_path()
    p.parent.mkdir(parents=True)
    p.write_text("this is = = not toml")
    s, warn = settings.load()
    assert warn and s == settings.Settings()
    assert p.with_suffix(".toml.bad").exists() and not p.exists()


def test_atomic_write_interrupted_keeps_old(tmp_path, monkeypatch):
    tmp_path = tmp_path / "w"
    tmp_path.mkdir()
    target = tmp_path / "meta.json"
    fsutil.atomic_write_json(target, {"v": 1})

    def boom(src, dst):
        raise KeyboardInterrupt  # simulates the process dying between write and rename

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        fsutil.atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]  # temp file cleaned up


def test_recording_create_update_reload(tmp_path):
    lib = Library(tmp_path / "data")
    rec = lib.create("Hola", "recorded", source="Mic")
    assert rec.folder.name == rec.id and len(rec.id) == 24
    rec.update(duration=12.5, crop_start=1.0)
    again = lib.get(rec.id)
    assert again.meta.duration == 12.5 and again.meta.crop_start == 1.0 and again.meta.title == "Hola"


def test_transcript_status_and_edits(tmp_path):
    lib = Library(tmp_path / "data")
    rec = lib.create("x", "imported")
    assert rec.transcript_status() == library.T_NONE
    rec.request_transcription(adapter=True)
    assert rec.transcript_status() == library.T_QUEUED
    fsutil.atomic_write_json(rec.path(library.PROGRESS), {"done": 1, "total": 4})
    assert rec.transcript_status() == library.T_RUNNING
    rec.path(library.REQUESTED).unlink()
    rec.path(library.PROGRESS).unlink()
    fsutil.atomic_write_json(rec.path(library.TRANSCRIPT), {"text": "hola mundo", "segments": []})
    assert rec.transcript_status() == library.T_DONE and rec.text() == "hola mundo"
    rec.save_edited("Hola, mundo.")
    assert rec.text() == "Hola, mundo." and rec.model_text() == "hola mundo" and rec.is_edited()
    rec.revert_edits()
    assert rec.text() == "hola mundo"


def test_salvage_folder_without_meta(tmp_path):
    lib = Library(tmp_path / "data")
    folder = lib.recordings_dir / "2026-01-01T00-00-00_abcd"
    (folder / "takes").mkdir(parents=True)
    (folder / "takes" / "take-001.raw").write_bytes(b"\0" * 100)
    recs = lib.all()
    assert len(recs) == 1 and recs[0].meta.state == library.NEEDS_FINALIZE and recs[0].meta.recovered


def test_index_rebuild_after_delete(tmp_path):
    lib = Library(tmp_path / "data")
    a = lib.create("Reunión con Ana", "recorded")
    b = lib.create("Notas", "imported")
    fsutil.atomic_write_json(b.path(library.TRANSCRIPT), {"text": "el presupuesto de marketing", "segments": []})
    idx = Index(lib)
    idx.sync()
    assert {r["id"] for r in idx.list()} == {a.id, b.id}
    assert [r["id"] for r in idx.list("reunion")] == [a.id]  # diacritics-insensitive
    assert [r["id"] for r in idx.list("presu")] == [b.id]  # prefix match in transcript
    idx.close()
    idx.path.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(idx.path) + suffix).unlink(missing_ok=True)
    idx2 = Index(lib)
    assert idx2.sync() == 2
    row = {r["id"]: r for r in idx2.list()}[b.id]
    assert row["transcript_status"] == "done"


def test_index_notices_changes_and_removals(tmp_path):
    lib = Library(tmp_path / "data")
    a = lib.create("A", "recorded")
    idx = Index(lib)
    idx.sync()
    assert idx.sync() == 0
    a.save_edited("nuevo texto")
    assert idx.sync() == 1
    lib.delete(a)
    assert idx.sync() == 1 and idx.list() == []


def test_delete_goes_to_freedesktop_trash(isolated_home, tmp_path):
    lib = Library(isolated_home / ".local/share/echo")
    rec = lib.create("borrar", "recorded")
    (rec.folder / "audio.flac").write_bytes(b"data")
    dest = lib.delete(rec)
    trash = isolated_home / ".local/share/Trash"
    assert dest == trash / "files" / rec.id and not rec.folder.exists()
    assert (dest / "audio.flac").read_bytes() == b"data"
    info = (trash / "info" / f"{rec.id}.trashinfo").read_text()
    assert info.startswith("[Trash Info]") and "Path=" in info


def test_delete_falls_back_to_a_folder_without_a_trash(isolated_home, monkeypatch):
    import send2trash

    def no_trash(path):
        raise OSError("no trash here")

    monkeypatch.setattr(send2trash, "send2trash", no_trash)
    monkeypatch.setattr("echo_app.library.sys.platform", "darwin")  # where send2trash is used
    lib = Library(isolated_home / "data")
    rec = lib.create("borrar", "recorded")
    dest = lib.delete(rec)
    assert dest == lib.data_dir / "trash" / rec.id and dest.is_dir() and not rec.folder.exists()

"""Watched folders: settled files are imported once, failures are reported once."""

import json
import time

import pytest

from echo_app import settings, watch
from echo_app.library import REQUESTED, Library
from test_ui import lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures


def _scan_until_quiet(scanner, folders, rounds=5, **kw):
    total = watch.ScanResult()
    for _ in range(rounds):
        res = scanner.scan(folders, **kw)
        total.imported += res.imported
        total.failed += res.failed
        total.duplicates += res.duplicates
        if not res.waiting:
            break
        time.sleep(scanner.stable_seconds + 0.05)
    return total


@pytest.fixture
def setup(tmp_path):
    lib_ = Library(tmp_path / "data")
    folder = tmp_path / "phone"
    folder.mkdir()
    return lib_, folder, watch.Scanner(lib_, stable_seconds=0.2)


def test_new_files_are_imported_once_settled(setup, tmp_path):
    lib, folder, scanner = setup
    wav(folder / "PTT-20261023-WA0001.opus", 1)
    first = scanner.scan([folder], auto_transcribe=False)
    assert not first.imported and first.waiting == 1  # just appeared: wait until it stops changing
    res = _scan_until_quiet(scanner, [folder], auto_transcribe=False)
    assert len(res.imported) == 1
    assert lib.all()[0].meta.title.startswith("WhatsApp voice note 2026-10-23")
    assert (folder / "PTT-20261023-WA0001.opus").exists()  # the original stays
    assert not _scan_until_quiet(scanner, [folder], auto_transcribe=False).imported  # not again
    ledger = json.loads((lib.data_dir / watch.LEDGER).read_text())
    assert str(folder / "PTT-20261023-WA0001.opus") in ledger[str(folder)]["handled"]


def test_a_screen_recording_in_a_watched_folder(setup):
    from test_video_import import make_video

    lib, folder, scanner = setup
    make_video(folder / "2026-09-23 15-02-29.mkv", ["-c:a", "flac"])
    res = _scan_until_quiet(scanner, [folder], auto_transcribe=False)
    assert len(res.imported) == 1
    rec = lib.all()[0]
    assert rec.meta.title == "Screen recording 2026-09-23 15:02" and rec.audio_path.suffix == ".flac"
    assert (folder / "2026-09-23 15-02-29.mkv").exists()


def test_a_growing_file_waits(setup):
    lib, folder, scanner = setup
    f = folder / "nota.wav"
    wav(f, 1)
    scanner.scan([folder], auto_transcribe=False)
    time.sleep(0.25)
    with open(f, "ab") as out:
        out.write(b"\0" * 1000)  # still being copied
    assert not scanner.scan([folder], auto_transcribe=False).imported


def test_duplicates_and_failures(setup):
    lib, folder, scanner = setup
    wav(folder / "a.wav", 1)
    wav(folder / "copia.wav", 1)  # same audio, different name
    (folder / "roto.mp3").write_bytes(b"not audio at all")
    (folder / "notas.txt").write_text("ignored")
    (folder / ".oculto.wav").write_bytes(b"x")
    res = _scan_until_quiet(scanner, [folder], auto_transcribe=False)
    assert len(res.imported) == 1 and res.duplicates == 1
    assert [r.source.name for r in res.failed] == ["roto.mp3"]
    assert "could not import roto.mp3" in watch.summary(res)
    # Reported once; tried again only when the file changes.
    assert not _scan_until_quiet(scanner, [folder], auto_transcribe=False).failed
    wav(folder / "roto.mp3", 2)
    res = _scan_until_quiet(scanner, [folder], auto_transcribe=False)
    assert [r.source.name for r in res.imported] == ["roto.mp3"]


def test_imports_are_queued_for_transcription(setup, monkeypatch):
    from echo_app import features

    lib, folder, scanner = setup
    monkeypatch.setattr(features, "transcription_installed", lambda: True)
    wav(folder / "x.wav", 1)
    res = _scan_until_quiet(scanner, [folder], auto_transcribe=True)
    assert res.imported[0].recording.path(REQUESTED).exists()


def test_cli_watch_polls(tmp_path, monkeypatch, capsys):
    from echo_app import cli

    folder = tmp_path / "in"
    folder.mkdir()
    settings.save(settings.Settings(data_dir=str(tmp_path / "data"), watch_dirs=[str(folder)], auto_transcribe=False))
    wav(folder / "uno.wav", 1)
    monkeypatch.setattr(watch.Scanner.__init__, "__defaults__", (0.1,))  # settle time
    real_sleep = time.sleep
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        if len(sleeps) > 3:
            raise KeyboardInterrupt
        real_sleep(min(s, 0.15))

    monkeypatch.setattr(watch.time, "sleep", sleep)
    assert cli.main(["import", "--watch", "--interval", "5"]) == 0
    out = capsys.readouterr().out
    assert f"Watching {folder}" in out and "+ uno.wav" in out


def test_window_imports_from_a_watched_folder(window, lib, tmp_path):
    folder = tmp_path / "sync"
    folder.mkdir()
    window.watcher.scanner.stable_seconds = 0.2
    window.watcher._settle.setInterval(300)
    window.watcher.configure([str(folder)])
    wav(folder / "voz.wav", 1)
    assert wait_until(lambda: any(r.meta.title == "voz" for r in lib.all()), 15)
    assert wait_until(lambda: window.model.rowCount() == 1, 5)
    assert "Imported 1 new file" in window.statusBar().currentMessage()


def test_settings_page_saves_folders(qapp, lib, tmp_path):
    from echo_app.ui.dialogs import SettingsDialog

    d = SettingsDialog(recording_active=False)
    d.watched.list.addItem(str(tmp_path))
    d.accept()
    assert settings.load()[0].watch_dirs == [str(tmp_path)]

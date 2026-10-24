import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from echo_app import importer
from echo_app.audio import ffmpeg
from echo_app.library import REQUESTED, Library

FORMATS = {
    # name: (extension, ffmpeg codec args)
    "whatsapp_opus": (".opus", ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000"]),
    "ogg_opus": (".ogg", ["-c:a", "libopus", "-ar", "48000"]),
    "m4a": (".m4a", ["-c:a", "aac", "-b:a", "64k"]),
    "mp3": (".mp3", ["-c:a", "libmp3lame", "-b:a", "64k"]),
    "amr": (".amr", ["-c:a", "libopencore_amrnb", "-ar", "8000", "-ab", "12.2k"]),
    "wav": (".wav", ["-c:a", "pcm_s16le"]),
    "flac": (".flac", ["-c:a", "flac"]),
    "webm": (".webm", ["-c:a", "libopus", "-ar", "48000"]),
    "wma": (".wma", ["-c:a", "wmav2"]),
}


def make_audio(path: Path, codec_args, seconds=2.0, freq=440):
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        f"sine=frequency={freq}:duration={seconds}", "-ac", "1", *codec_args, str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"encoder unavailable: {r.stderr.strip()[-120:]}")
    return path


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "data")


@pytest.mark.parametrize("name", list(FORMATS))
def test_import_each_format(lib, tmp_path, name):
    ext, args = FORMATS[name]
    src = make_audio(tmp_path / f"in{ext}", args)
    before = ffmpeg.sha256_file(src)
    r = importer.import_file(lib, src)
    assert r.status == importer.IMPORTED, r.message
    rec = r.recording
    assert rec.audio_path.name == f"audio{ext}"
    assert ffmpeg.sha256_file(rec.audio_path) == before == rec.meta.sha256
    assert ffmpeg.sha256_file(src) == before and src.exists()  # copied, not moved
    assert rec.meta.duration == pytest.approx(2.0, abs=0.15)
    assert rec.meta.origin == "imported"


def test_non_audio_rejected_rest_continue(lib, tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 not audio")
    a = make_audio(tmp_path / "a.mp3", FORMATS["mp3"][1])
    b = make_audio(tmp_path / "b.wav", FORMATS["wav"][1], freq=880)
    results = importer.import_paths(lib, [pdf, a, b], auto_transcribe=False)
    assert [r.status for r in results] == [importer.REJECTED, importer.IMPORTED, importer.IMPORTED]
    assert "not a readable audio file" in results[0].message
    assert len(lib.all()) == 2


def test_duplicate_skipped(lib, tmp_path):
    a = make_audio(tmp_path / "PTT-20261023-WA0003.opus", FORMATS["whatsapp_opus"][1])
    copy = tmp_path / "again.opus"
    shutil.copy(a, copy)
    first = importer.import_file(lib, a)
    second = importer.import_file(lib, copy)
    assert second.status == importer.DUPLICATE and first.recording.meta.title in second.message
    assert len(lib.all()) == 1
    assert not any((lib.data_dir / importer.STAGING).iterdir())


def test_folder_import_recursive_skips_hidden(lib, tmp_path):
    d = tmp_path / "notes"
    (d / "sub").mkdir(parents=True)
    (d / ".hidden").mkdir()
    make_audio(d / "one.opus", FORMATS["whatsapp_opus"][1])
    make_audio(d / "sub" / "two.m4a", FORMATS["m4a"][1], freq=500)
    make_audio(d / ".hidden" / "three.mp3", FORMATS["mp3"][1], freq=600)
    (d / "readme.txt").write_text("hi")
    results = importer.import_paths(lib, [d], auto_transcribe=False)
    assert sorted(r.source.name for r in results) == ["one.opus", "two.m4a"]


@pytest.mark.parametrize("name,title,date", [
    ("WhatsApp Audio 2026-10-23 at 14.32.11.opus", "WhatsApp voice note 2026-10-23 14:32", datetime(2026, 10, 23, 14, 32, 11)),
    ("WhatsApp Ptt 2026-01-05 at 9.03.44 AM.ogg", "WhatsApp voice note 2026-01-05 09:03", datetime(2026, 1, 5, 9, 3, 44)),
    ("WhatsApp Audio 2026-01-05 at 9.03.44 PM.opus", "WhatsApp voice note 2026-01-05 21:03", datetime(2026, 1, 5, 21, 3, 44)),
    ("WhatsApp Audio 2026-01-05 at 12.10.00 a. m..ogg", "WhatsApp voice note 2026-01-05 00:10", datetime(2026, 1, 5, 0, 10)),
    ("WhatsApp Audio 2026-01-05 a las 18.10.00.ogg", "WhatsApp voice note 2026-01-05 18:10", datetime(2026, 1, 5, 18, 10)),
    ("PTT-20250102-WA0001.opus", "WhatsApp voice note 2025-01-02", datetime(2025, 1, 2)),
    ("AUD-20250102-WA0007.m4a", "WhatsApp audio 2025-01-02", datetime(2025, 1, 2)),
])
def test_whatsapp_names(tmp_path, name, title, date):
    p = tmp_path / name
    p.write_bytes(b"x")
    os.utime(p, (datetime(2026, 6, 1).timestamp(),) * 2)  # different day than the name
    t, d = importer.title_and_date(p)
    assert (t, d) == (title, date)


def test_android_name_uses_mtime_for_time_of_day_when_same_day(tmp_path):
    p = tmp_path / "PTT-20250102-WA0001.opus"
    p.write_bytes(b"x")
    ts = datetime(2025, 1, 2, 18, 45).timestamp()
    os.utime(p, (ts, ts))
    assert importer.title_and_date(p) == ("WhatsApp voice note 2025-01-02 18:45", datetime(2025, 1, 2, 18, 45))


def test_plain_name_uses_mtime(tmp_path):
    p = tmp_path / "reunion_equipo_lunes.mp3"
    p.write_bytes(b"x")
    ts = datetime(2024, 3, 4, 10, 0).timestamp()
    os.utime(p, (ts, ts))
    assert importer.title_and_date(p) == ("reunion equipo lunes", datetime(2024, 3, 4, 10, 0))


def test_imported_created_date_from_name(lib, tmp_path):
    src = make_audio(tmp_path / "WhatsApp Audio 2026-10-23 at 14.32.11.opus", FORMATS["whatsapp_opus"][1])
    rec = importer.import_file(lib, src).recording
    assert rec.meta.created.startswith("2026-10-23T14:32:11")


def test_interrupted_copy_leaves_no_recording(lib, tmp_path, monkeypatch):
    src = make_audio(tmp_path / "big.wav", FORMATS["wav"][1], seconds=5)

    def dying_copy(s, d):
        Path(d).write_bytes(Path(s).read_bytes()[:1000])
        raise KeyboardInterrupt  # process killed mid-copy

    monkeypatch.setattr(importer, "_copy_verified", dying_copy)
    with pytest.raises(KeyboardInterrupt):
        importer.import_file(lib, src)
    assert lib.all() == []
    importer.clean_staging(lib)
    assert not (lib.data_dir / importer.STAGING).exists()


def test_auto_transcribe_marker(lib, tmp_path):
    src = make_audio(tmp_path / "a.mp3", FORMATS["mp3"][1])
    (r,) = importer.import_paths(lib, [src], auto_transcribe=True)
    assert (r.recording.folder / REQUESTED).exists()
    src2 = make_audio(tmp_path / "b.mp3", FORMATS["mp3"][1], freq=300)
    (r2,) = importer.import_paths(lib, [src2], auto_transcribe=False)
    assert not (r2.recording.folder / REQUESTED).exists()

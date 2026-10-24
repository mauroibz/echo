import subprocess

import numpy as np
import pytest

from echo_app import export
from echo_app.audio import ffmpeg, peaks
from echo_app.library import TRANSCRIPT, Library


def tone_then_silence(path):
    sr = 8000
    t = np.arange(sr * 2)
    a = np.concatenate([(np.sin(t * 0.3) * 10000).astype(np.int16), np.zeros(sr, np.int16),
                        (np.sin(t * 0.2) * 10000).astype(np.int16)])
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                    str(path)], input=a.tobytes(), check=True)
    return path


@pytest.fixture
def rec(tmp_path):
    from echo_app import importer

    lib = Library(tmp_path / "data")
    return importer.import_file(lib, tone_then_silence(tmp_path / "Reunión: plan.wav")).recording


def test_export_uncropped_is_identical_copy(rec, tmp_path):
    out = export.export_audio(rec, tmp_path / "out.flac")
    assert out.suffix == ".wav" and ffmpeg.sha256_file(out) == rec.meta.sha256


def test_export_cropped_is_exact_flac_span(rec, tmp_path):
    rec.update(crop_start=1.0, crop_end=3.5)
    before = ffmpeg.sha256_file(rec.audio_path)
    out = export.export_audio(rec, tmp_path / "out.wav")
    assert out.suffix == ".flac"
    assert ffmpeg.probe(out).duration == pytest.approx(2.5, abs=0.01)
    assert ffmpeg.sha256_file(rec.audio_path) == before


def test_export_transcript_txt_and_md(rec, tmp_path):
    rec.path(TRANSCRIPT).write_text('{"text": "Hola.\\n\\nAdiós.", "segments": []}')
    t = export.export_transcript(rec, tmp_path / "t.txt")
    assert t.read_text() == "Hola.\n\nAdiós.\n"
    rec.save_edited("Hola, mundo.")
    m = export.export_transcript(rec, tmp_path / "t.md")
    assert m.read_text().startswith("# Reunión: plan\n\n_") and m.read_text().endswith("Hola, mundo.\n")
    assert export.suggested_name(rec, ".txt") == "Reunión_ plan.txt"


def test_peaks_cached_and_snap_finds_pause(rec, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    p = peaks.compute(rec.audio_path, rec.meta.sha256)
    assert p.shape == (500, 2)  # 5 s at 100 buckets per second
    assert (tmp_path / "cache/echo/peaks" / f"{rec.meta.sha256}.npy").exists()
    assert np.array_equal(peaks.compute(rec.audio_path, rec.meta.sha256), p)
    # Silence is 2.0-3.0 s: a point at 1.85 s snaps into it.
    assert 2.0 <= peaks.snap(p, 1.85) <= 2.2
    # In the middle of loud audio with no pause nearby, the point stays close.
    assert abs(peaks.snap(p, 0.8) - 0.8) <= 0.3


def test_suggested_names_are_safe_on_windows(tmp_path):
    from echo_app.export import suggested_name
    from echo_app.library import Library

    lib = Library(tmp_path / "data")
    for title, expected in (("CON", "_CON.txt"), ("nul.backup", "_nul.backup.txt"), ("Notas...", "Notas.txt"),
                            ("a/b: c?", "a_b_ c_.txt"), ("Lpt3 ", "_Lpt3.txt")):
        assert suggested_name(lib.create(title, "imported"), ".txt") == expected, title

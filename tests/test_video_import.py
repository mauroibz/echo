"""Video files: the sound is extracted, copied when the codec allows, verified; the video is only read."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from echo_app import importer
from echo_app.audio import ffmpeg
from echo_app.library import Library


def make_video(path: Path, audio_args, seconds=2.0, audio=True, extra=()):
    """A short test-card video with a sine tone, from ffmpeg's lavfi sources."""
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=10:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "mpeg4", *(["-ac", "2", *audio_args] if audio else []), *extra, "-shortest", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"encoder unavailable: {r.stderr.strip()[-120:]}")
    return path


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "data")


CASES = {
    # name: (video file, audio codec args, stored extension, method, stored codec)
    "obs_aac": ("2026-09-23 15-02-29.mp4", ["-c:a", "aac", "-b:a", "128k"], ".m4a", "copy", "aac"),
    "opus_mkv": ("call.mkv", ["-c:a", "libopus", "-ar", "48000"], ".opus", "copy", "opus"),
    "mp3_avi": ("old.avi", ["-c:a", "libmp3lame"], ".mp3", "copy", "mp3"),
    "vorbis_mkv": ("clip.mkv", ["-c:a", "libvorbis"], ".ogg", "copy", "vorbis"),
    "flac_mkv": ("lossless.mkv", ["-c:a", "flac"], ".flac", "copy", "flac"),
    "pcm_mov": ("camera.mov", ["-c:a", "pcm_s16le"], ".flac", "encode", "flac"),
    "ac3_mkv": ("movie.mkv", ["-c:a", "ac3"], ".opus", "encode", "opus"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_sound_stored_by_codec(lib, tmp_path, name):
    fname, args, ext, method, codec = CASES[name]
    src = make_video(tmp_path / fname, args)
    before = ffmpeg.sha256_file(src)
    fracs = []
    r = importer.import_file(lib, src, progress=fracs.append)
    assert r.status == importer.IMPORTED, r.message
    rec = r.recording
    assert rec.audio_path.name == f"audio{ext}"
    out = ffmpeg.probe(rec.audio_path)
    assert out.codec == codec and not out.has_video
    assert rec.meta.duration == pytest.approx(2.0, abs=0.15)
    assert rec.meta.sha256 == ffmpeg.sha256_file(rec.audio_path)
    ef = rec.meta.extracted_from
    assert ef == {"name": fname, "sha256": before, "size": src.stat().st_size, "track": 1, "method": method}
    assert ffmpeg.sha256_file(src) == before  # the video is only read
    assert fracs and all(0 <= f <= 1 for f in fracs)
    assert not any((lib.data_dir / importer.STAGING).iterdir())


def test_copy_from_mpegts_verified_by_sound(lib, tmp_path):
    # ADTS AAC loses its frame headers in .m4a, so the packets differ while the sound is the same.
    src = make_video(tmp_path / "capture.ts", ["-c:a", "aac"])
    r = importer.import_file(lib, src)
    assert r.status == importer.IMPORTED, r.message
    assert r.recording.meta.extracted_from["method"] == "copy"
    assert r.recording.audio_path.suffix == ".m4a"


def test_cover_art_is_not_a_video(lib, tmp_path):
    art = tmp_path / "cover.png"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=red:size=64x64", "-frames:v", "1", str(art)], check=True)
    song = tmp_path / "song.m4a"
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-i", str(art), "-map", "0", "-map", "1",
                        "-c:a", "aac", "-c:v", "png", "-disposition:v", "attached_pic", str(song)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(r.stderr[-120:])
    assert not ffmpeg.probe(song).has_video
    rec = importer.import_file(lib, song).recording
    assert rec.meta.extracted_from is None
    assert ffmpeg.sha256_file(rec.audio_path) == ffmpeg.sha256_file(song)  # byte for byte, as before


def test_default_track_is_used(lib, tmp_path):
    src = tmp_path / "obs-tracks.mkv"
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
                        "-map", "0", "-map", "1", "-map", "2", "-c:v", "mpeg4", "-c:a", "flac",
                        "-disposition:a:0", "0", "-disposition:a:1", "default", str(src)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(r.stderr[-120:])
    info = ffmpeg.probe(src)
    assert [t.default for t in info.tracks] == [False, True]
    rec = importer.import_file(lib, src).recording
    assert rec.meta.extracted_from["track"] == 2
    assert rec.meta.duration == pytest.approx(2.0, abs=0.15)  # the 2-second track, not the 1-second one


def test_video_without_sound_rejected(lib, tmp_path):
    src = make_video(tmp_path / "silent.mp4", [], audio=False)
    r = importer.import_file(lib, src)
    assert r.status == importer.REJECTED and r.message == "this video has no sound"
    assert lib.all() == []


def test_same_video_twice_is_a_duplicate_before_extraction(lib, tmp_path, monkeypatch):
    src = make_video(tmp_path / "meeting.mp4", ["-c:a", "aac"])
    first = importer.import_file(lib, src)

    def no_extraction(*a, **k):
        raise AssertionError("extracted a known video")

    monkeypatch.setattr(ffmpeg, "extract_audio", no_extraction)
    again = importer.import_file(lib, src)
    assert again.status == importer.DUPLICATE and first.recording.meta.title in again.message
    # The extracted file dropped on its own is the same recording too.
    dropped = tmp_path / "copy.m4a"
    dropped.write_bytes(first.recording.audio_path.read_bytes())
    assert importer.import_file(lib, dropped).status == importer.DUPLICATE
    assert len(lib.all()) == 1


def test_failed_verification_leaves_nothing(lib, tmp_path, monkeypatch):
    src = make_video(tmp_path / "meeting.mkv", ["-c:a", "libopus", "-ar", "48000"], seconds=3)
    real = ffmpeg.extract_audio

    def damaged(s, track, dest, opts, progress=None):
        real(s, track, dest, opts, progress)
        data = Path(dest).read_bytes()
        Path(dest).write_bytes(data[: len(data) // 2])  # half the sound went missing

    monkeypatch.setattr(ffmpeg, "extract_audio", damaged)
    r = importer.import_file(lib, src)
    assert r.status == importer.REJECTED and "could not extract the sound" in r.message
    assert lib.all() == []
    assert not any((lib.data_dir / importer.STAGING).iterdir())


def test_killed_during_extraction_leaves_no_recording(lib, tmp_path, monkeypatch):
    src = make_video(tmp_path / "meeting.mp4", ["-c:a", "aac"])

    def killed(s, track, dest, opts, progress=None):
        Path(dest).write_bytes(b"\0" * 1000)
        raise KeyboardInterrupt  # process killed mid-extraction

    monkeypatch.setattr(ffmpeg, "extract_audio", killed)
    with pytest.raises(KeyboardInterrupt):
        importer.import_file(lib, src)
    assert lib.all() == []
    assert any((lib.data_dir / importer.STAGING).iterdir())
    importer.clean_staging(lib)
    assert not (lib.data_dir / importer.STAGING).exists()


def test_folder_with_videos(lib, tmp_path):
    d = tmp_path / "meetings"
    d.mkdir()
    make_video(d / "monday.mkv", ["-c:a", "flac"])
    make_video(d / "tuesday.mov", ["-c:a", "aac"])
    (d / "slide.png").write_bytes(b"\x89PNG")
    seen = []
    results = importer.import_paths(lib, [d], progress=lambda *a: seen.append(a), auto_transcribe=False)
    assert sorted(r.source.name for r in results) == ["monday.mkv", "tuesday.mov"]
    assert all(r.status == importer.IMPORTED for r in results)
    assert any(len(a) == 4 for a in seen)  # progress within a file


@pytest.mark.parametrize("name,title,date", [
    ("2026-09-23 15-02-29.mp4", "Screen recording 2026-09-23 15:02", datetime(2026, 9, 23, 15, 2, 29)),
    ("2026-05-31 23-31-58.mkv", "Screen recording 2026-05-31 23:31", datetime(2026, 5, 31, 23, 31, 58)),
])
def test_obs_names(tmp_path, name, title, date):
    p = tmp_path / name
    p.write_bytes(b"x")
    os.utime(p, (datetime(2026, 6, 1).timestamp(),) * 2)
    assert importer.title_and_date(p) == (title, date)


def test_obs_like_audio_name_keeps_plain_rule(tmp_path):
    p = tmp_path / "2026-09-23 15-02-29.flac"  # not a screen recording
    p.write_bytes(b"x")
    assert importer.title_and_date(p)[0] == "2026-09-23 15-02-29"

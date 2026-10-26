"""Call recordings: the input and the computer audio as paired takes, finalized into two channels.

The supervisor runs for real with the fake capture; the computer audio writes negative samples
(fake_capture.py "negative") and the input positive ones, so each channel's origin is checkable.
"""

import array
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from echo_app import recorder
from echo_app.audio import ffmpeg, tracks
from echo_app.library import READY, Library

FAKE = Path(__file__).with_name("fake_capture.py")
RATE = 16000
KILL = getattr(signal, "SIGKILL", signal.SIGTERM)
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX signals")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_CAPTURE_CMD", f"{sys.executable} -P {FAKE} {{path}} {{bps}}")
    monkeypatch.setenv("ECHO_CAPTURE_OUT_CMD", f"{sys.executable} -P {FAKE} {{path}} {{bps}} negative")
    monkeypatch.delenv("FAKE_MODE", raising=False)
    lib = Library(tmp_path / "data")
    yield lib
    for rec in lib.all():
        s = recorder.Session(rec)
        if s.alive():
            os.kill(s.supervisor_pid, KILL)
        for t in (recorder.load_session(rec) or {}).get("takes", []):
            for pid in (t.get("pid"), (t.get("out") or {}).get("pid")):
                try:
                    os.kill(pid, KILL)
                except (ProcessLookupError, TypeError):
                    pass


def wait_for(cond, timeout=10.0, step=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(step)
    return False


def channels_of(path: Path) -> tuple[array.array, array.array]:
    raw = subprocess.run(ffmpeg.decode_cmd(path, RATE, 2), capture_output=True, check=True).stdout
    a = array.array("h", raw)
    return a[0::2], a[1::2]


def current_take(rec) -> dict:
    return recorder.load_session(rec)["takes"][-1]


def check_two_channels(rec, min_seconds: float):
    m = rec.reload().meta
    assert m.state == READY and m.channels == 2 and m.tracks == ["mic", "computer"]
    mic, comp = channels_of(rec.audio_path)
    assert len(mic) == round(m.duration * RATE) and m.duration > min_seconds
    assert all(v >= 0 for v in mic), "the input is on channel 1, with silence only as padding"
    assert all(v <= 0 for v in comp), "the computer audio is on channel 2"
    assert sum(1 for v in comp if v < 0) > 0.8 * len(comp)
    return m, mic, comp


def test_call_record_pause_resume_stop(lib):
    s = recorder.start(lib, rate=RATE, computer_audio=True, title="call")
    assert wait_for(lambda: s.status().get("out_take"))
    assert s.status()["tracks"] == ["mic", "computer"]
    assert s.status()["source"].endswith("+ computer audio")
    time.sleep(1.2)
    s.pause()
    assert wait_for(lambda: s.status()["state"] == recorder.S_PAUSED)
    s.resume()
    assert wait_for(lambda: s.status()["state"] == recorder.S_RECORDING)
    time.sleep(1.2)
    takes = recorder.load_session(s.rec)["takes"]
    assert s.stop(wait=20) == "ready"
    m, mic, comp = check_two_channels(s.rec, 2.0)
    assert len(takes) == 2 and all(t["out"]["file"].startswith("out-") for t in takes)
    assert takes[0]["align"] == "end"  # paused together
    assert m.sha256 == ffmpeg.sha256_file(s.rec.audio_path)
    assert 2.0 < m.duration < 3.4, m.duration  # elapsed excludes the pause, as for one track


@posix_only
def test_out_capture_killed_restarts_both(lib):
    s = recorder.start(lib, rate=RATE, computer_audio=True)
    assert wait_for(lambda: s.status().get("out_take"))
    time.sleep(1.0)
    first = current_take(s.rec)
    os.kill(first["out"]["pid"], KILL)
    assert wait_for(lambda: current_take(s.rec)["file"] != first["file"] and current_take(s.rec).get("out"))
    taken = recorder.load_session(s.rec)["takes"]
    assert taken[0]["end_reason"] == "interrupted" and "align" not in taken[0]
    time.sleep(1.0)
    assert s.stop(wait=20) == "ready"
    m, mic, comp = check_two_channels(s.rec, 1.5)
    assert any("Computer audio capture stopped" in g["cause"] for g in m.gaps)


@posix_only
def test_out_capture_stalled_restarts_both(lib):
    s = recorder.start(lib, rate=RATE, computer_audio=True)
    assert wait_for(lambda: s.status().get("out_take"))
    first = current_take(s.rec)
    os.kill(first["out"]["pid"], signal.SIGSTOP)
    try:
        # A frozen capture ignores SIGINT and takes seconds to kill; the heartbeat goes on meanwhile.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and current_take(s.rec)["file"] == first["file"]:
            assert s.alive(), "the supervisor must keep answering while it stops a frozen capture"
            time.sleep(0.05)
        assert current_take(s.rec)["file"] != first["file"]
    finally:
        try:
            os.kill(first["out"]["pid"], signal.SIGCONT)
        except ProcessLookupError:
            pass
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    assert any("Computer audio capture stalled" in g["cause"] for g in m.gaps)


def test_out_capture_cannot_start(lib, monkeypatch):
    monkeypatch.setenv("ECHO_CAPTURE_OUT_CMD", "/nonexistent/capture {path}")
    s = recorder.start(lib, rate=RATE, computer_audio=True)
    assert wait_for(lambda: "Computer audio is not being recorded" in (s.status().get("warning") or ""))
    time.sleep(1.0)
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    mic, comp = channels_of(s.rec.audio_path)
    assert m.channels == 2 and max(mic) > 0 and not any(comp), "input recorded, channel 2 silent"
    assert any("Could not record the computer audio" in g["cause"] for g in m.gaps)


@posix_only
def test_supervisor_killed_both_captures_adopted(lib):
    s = recorder.start(lib, rate=RATE, computer_audio=True)
    assert wait_for(lambda: s.status().get("out_take"))
    time.sleep(0.8)
    take = current_take(s.rec)
    os.kill(s.supervisor_pid, KILL)
    assert wait_for(lambda: not s.alive(), timeout=5)
    assert dict(recorder.recover_all(lib))[s.rec.id] == "adopted"
    assert wait_for(s.alive)
    assert current_take(s.rec)["file"] == take["file"], "the same pair continues"
    time.sleep(0.8)
    assert s.stop(wait=20) == "ready"
    m, _, _ = check_two_channels(s.rec, 1.4)
    assert not m.recovered


@posix_only
def test_supervisor_and_out_capture_killed_new_pair(lib):
    s = recorder.start(lib, rate=RATE, computer_audio=True)
    assert wait_for(lambda: s.status().get("out_take"))
    time.sleep(0.8)
    take = current_take(s.rec)
    os.kill(s.supervisor_pid, KILL)
    os.kill(take["out"]["pid"], KILL)
    assert wait_for(lambda: not s.alive(), timeout=5)
    assert dict(recorder.recover_all(lib))[s.rec.id] == "adopted"
    assert wait_for(lambda: s.alive() and current_take(s.rec)["file"] != take["file"]
                    and current_take(s.rec).get("out"))
    time.sleep(0.8)
    assert s.stop(wait=20) == "ready"
    check_two_channels(s.rec, 1.4)


@posix_only
def test_everything_killed_finalized_with_both_channels(lib):
    s = recorder.start(lib, rate=RATE, computer_audio=True)
    assert wait_for(lambda: s.status().get("out_take"))
    time.sleep(1.0)
    take = current_take(s.rec)
    for pid in (s.supervisor_pid, take["pid"], take["out"]["pid"]):
        os.kill(pid, KILL)
    assert wait_for(lambda: not s.alive(), timeout=5)
    time.sleep(0.2)
    assert dict(recorder.recover_all(lib))[s.rec.id] == "finalized"
    m, _, _ = check_two_channels(s.rec, 0.8)
    assert m.recovered


def test_one_track_recordings_unchanged(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(0.8)
    assert s.status().get("out_take") is None
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    assert m.channels == 1 and m.tracks is None
    assert not list(s.rec.folder.glob("out-*"))


# ---- pairs, alignment and interleaving ------------------------------------------------------------

def _raw(path: Path, values) -> Path:
    path.write_bytes(array.array("h", values).tobytes())
    return path


def test_pair_aligned_at_end_pads_the_start(tmp_path):
    p = tracks.Pair(_raw(tmp_path / "take-001.raw", [1, 2, 3, 4]), _raw(tmp_path / "out-001.raw", [-1, -2]),
                    align_end=True)
    out = array.array("h", b"".join(tracks.interleave([p])))
    assert list(out[0::2]) == [1, 2, 3, 4] and list(out[1::2]) == [0, 0, -1, -2]


def test_pair_aligned_at_start_pads_the_end_and_shifts_markers(tmp_path):
    # The computer audio is longer: the input gets silence after it, and the next pair moves on.
    a = tracks.Pair(_raw(tmp_path / "take-001.raw", [1, 2]), _raw(tmp_path / "out-001.raw", [-1, -2, -3]))
    b = tracks.Pair(_raw(tmp_path / "take-002.raw", [5, 6]), None)
    out = array.array("h", b"".join(tracks.interleave([a, b])))
    assert list(out[0::2]) == [1, 2, 0, 5, 6] and list(out[1::2]) == [-1, -2, -3, 0, 0]
    at = tracks.time_map([a, b], rate=1)
    assert at(1) == 1 and at(2) == 3 and at(3) == 4  # the input's second 2 is the file's second 3


def test_pairs_found_by_number_with_missing_halves(tmp_path):
    _raw(tmp_path / "take-001.raw", [1])
    _raw(tmp_path / "out-002.raw", [-1])
    _raw(tmp_path / "take-002.raw", [2])
    _raw(tmp_path / "out-003.raw", [-3])
    ps = tracks.pairs(tmp_path, {"take-002.raw"})
    assert [(p.mic and p.mic.name, p.out and p.out.name, p.align_end) for p in ps] == [
        ("take-001.raw", None, False), ("take-002.raw", "out-002.raw", True), (None, "out-003.raw", False)]


def test_interleaving_an_hour_is_quick(tmp_path):
    """An hour at 48 kHz, both tracks: measured 1.0 s on the development machine (the FLAC encode takes far longer)."""
    n = 48000 * 3600
    mic, out = tmp_path / "take-001.raw", tmp_path / "out-001.raw"
    for p in (mic, out):
        with open(p, "wb") as f:
            f.truncate(n * 2)
    t = time.perf_counter()
    total = sum(len(c) for c in tracks.interleave([tracks.Pair(mic, out, True)]))
    elapsed = time.perf_counter() - t
    assert total == n * 4
    assert elapsed < 30, elapsed


# ---- mixing: playback, waveform and transcription hear both sides ---------------------------------

def _call_file(tmp_path, left: str, right: str, seconds: float = 1.0) -> Path:
    path = tmp_path / "call.flac"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc='{left}|{right}':s={RATE}:d={seconds}", "-c:a", "flac", str(path)], check=True)
    return path


def _peak(raw: bytes) -> float:
    return max(abs(v) for v in array.array("h", raw)) / 32768


def test_decode_mix_keeps_each_side_at_its_level(tmp_path):
    # The input alone for the first half, the call alone for the second.
    path = _call_file(tmp_path, "if(lt(t,0.5),0.4*sin(2*PI*300*t),0)", "if(gte(t,0.5),0.3*sin(2*PI*500*t),0)")
    mixed = subprocess.run(ffmpeg.decode_cmd(path, RATE, mix=True), capture_output=True, check=True).stdout
    averaged = subprocess.run(ffmpeg.decode_cmd(path, RATE), capture_output=True, check=True).stdout
    half = len(mixed) // 2
    assert abs(_peak(mixed[:half]) - 0.4) < 0.01 and abs(_peak(mixed[half:]) - 0.3) < 0.01
    assert abs(_peak(averaged[:half]) - 0.2) < 0.01  # what -ac 1 alone would give: 6 dB down


def test_playback_mix_in_both_ears_without_clipping(tmp_path):
    from echo_app.audio import playback

    assert playback._filters(1.0, 1.0, mix=True) == ["-af", f"{playback.MIX_STEREO},{playback.LIMITER}"]
    path = _call_file(tmp_path, "0.7*sin(2*PI*300*t)", "0.7*sin(2*PI*300*t)")  # both sides peak together
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), *playback._filters(1.0, 1.0, mix=True),
           "-f", "s16le", "-ac", "2", "-ar", str(playback.RATE), "pipe:1"]
    a = array.array("h", subprocess.run(cmd, capture_output=True, check=True).stdout)
    left, right = a[0::2], a[1::2]
    assert list(left) == list(right)
    assert max(abs(v) for v in left) < 32767


def test_waveform_of_a_call_shows_both_sides(tmp_path, monkeypatch):
    from echo_app.audio import peaks

    path = _call_file(tmp_path, "0", "0.5*sin(2*PI*300*t)")  # only the call speaks
    mixed = peaks.compute(path, mix=True)
    assert mixed[:, 1].max() > 0.45 * 32768


def test_worker_transcribes_the_sum(tmp_path):
    from echo_app import importer
    from echo_app.worker import service

    lib = Library(tmp_path / "data")
    rec = importer.import_file(lib, _call_file(tmp_path, "0.4*sin(2*PI*300*t)", "0")).recording
    rec.update(tracks=["mic", "computer"])
    audio, _ = service.decode(rec)
    assert abs(int(abs(audio).max()) / 32768 - 0.4) < 0.01


# ---- command line ---------------------------------------------------------------------------------

def test_cli_record_call_and_info_json(lib, capsys):
    import json

    from echo_app import cli, settings

    settings.save(settings.Settings(data_dir=str(lib.data_dir), sample_rate=RATE))
    assert cli.main(["record", "--computer-audio", "--title", "llamada"]) == 0
    s = recorder.active(lib)
    assert s is not None and s.rec.meta.source.endswith("+ computer audio")
    time.sleep(0.8)
    assert cli.main(["stop"]) == 0
    capsys.readouterr()
    assert cli.main(["info", s.rec.id, "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["tracks"] == ["mic", "computer"]
    assert s.rec.reload().meta.channels == 2


def test_cli_follows_the_setting_unless_told(lib, capsys):
    from echo_app import cli, settings

    settings.save(settings.Settings(data_dir=str(lib.data_dir), sample_rate=RATE, computer_audio=True))
    for argv, tracks_ in ((["record"], ["mic", "computer"]), (["record", "--no-computer-audio"], None),
                          (["record", "--quick-note"], None)):
        assert cli.main(argv) == 0
        s = recorder.active(lib)
        time.sleep(0.5)
        assert cli.main(["stop"]) == 0
        assert s.rec.reload().meta.tracks == tracks_, argv


def test_refused_without_output_recording(lib, monkeypatch):
    from echo_app.audio import backend

    monkeypatch.setattr(backend.CommandBackend, "records_outputs", False)
    assert not recorder.can_add_computer_audio()
    with pytest.raises(recorder.RecorderError, match="cannot record the computer audio"):
        recorder.start(lib, rate=RATE, computer_audio=True)

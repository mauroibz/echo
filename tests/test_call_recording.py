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
        assert wait_for(lambda: current_take(s.rec)["file"] != first["file"], timeout=15)
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

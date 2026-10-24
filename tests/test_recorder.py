"""Recording engine tests. They run real supervisor processes with a fake capture command."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from echo_app import recorder
from echo_app.audio import ffmpeg
from echo_app.library import NEEDS_FINALIZE, READY, RECORDING, Library

FAKE = Path(__file__).with_name("fake_capture.py")
RATE = 16000  # keeps tests light; the engine is rate-agnostic


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_CAPTURE_CMD", f"{sys.executable} -P {FAKE} {{path}} {{bps}}")
    monkeypatch.delenv("FAKE_MODE", raising=False)
    lib = Library(tmp_path / "data")
    yield lib
    # Never leave processes behind.
    for rec in lib.all():
        s = recorder.Session(rec)
        if s.alive():
            os.kill(s.supervisor_pid, signal.SIGKILL)
        for t in (recorder.load_session(rec) or {}).get("takes", []):
            try:
                os.kill(t["pid"], signal.SIGKILL)
            except (ProcessLookupError, TypeError):
                pass


def wait_for(cond, timeout=10.0, step=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(step)
    return False


def decoded_frames(path: Path) -> int:
    out = subprocess.run(ffmpeg.decode_cmd(path, RATE), capture_output=True, check=True).stdout
    return len(out) // 2


def test_record_pause_resume_stop(lib):
    s = recorder.start(lib, rate=RATE, channels=1, title="t")
    assert s.status()["state"] == recorder.S_RECORDING
    time.sleep(1.5)
    s.pause()
    assert wait_for(lambda: s.status()["state"] == recorder.S_PAUSED)
    time.sleep(1.0)
    s.resume()
    assert wait_for(lambda: s.status()["state"] == recorder.S_RECORDING)
    time.sleep(1.5)
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    assert m.state == READY and not s.rec.takes_dir.exists()
    assert 2.7 < m.duration < 3.5, m.duration  # paused time excluded
    assert decoded_frames(s.rec.audio_path) == round(m.duration * RATE)
    pauses = [g for g in m.gaps if g["kind"] == "pause"]
    assert len(pauses) == 1 and 0.8 < pauses[0]["seconds"] < 1.6
    assert m.sha256 == ffmpeg.sha256_file(s.rec.audio_path)


def test_only_one_active_recording(lib):
    s = recorder.start(lib, rate=RATE)
    with pytest.raises(recorder.RecorderError, match="Already recording"):
        recorder.start(lib, rate=RATE)
    s.stop(wait=20)


def test_capture_death_restarts_and_notes_gap(lib, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "die:1")
    monkeypatch.setenv("FAKE_MODE_ONCE", str(tmp_path / "died-once"))
    s = recorder.start(lib, rate=RATE)
    time.sleep(3.5)
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    causes = [g["cause"] for g in m.gaps]
    assert any("stopped unexpectedly" in c for c in causes), causes
    assert 2.5 < m.duration < 3.6


def test_capture_stall_restarts(lib, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "stall:1")
    monkeypatch.setenv("FAKE_MODE_ONCE", str(tmp_path / "stalled-once"))
    s = recorder.start(lib, rate=RATE)
    assert wait_for(lambda: len(recorder.take_files(s.rec)) >= 2, timeout=12)
    time.sleep(1.0)
    assert s.stop(wait=20) == "ready"
    causes = [g["cause"] for g in s.rec.reload().meta.gaps]
    assert any("stalled" in c for c in causes), causes


def _make_takes(lib, chunks):
    rec = lib.create("x", "recorded", state=RECORDING, sample_rate=RATE, channels=1)
    rec.takes_dir.mkdir()
    from echo_app.fsutil import atomic_write_json
    atomic_write_json(recorder.session_path(rec), {"rate": RATE, "channels": 1, "takes": [], "events": []})
    for i, data in enumerate(chunks, 1):
        (rec.takes_dir / f"take-{i:03d}.raw").write_bytes(data)
    return rec


def test_finalize_truncates_partial_frames_and_concatenates(lib):
    a = bytes(range(256)) * 100  # 25600 bytes
    b = b"\x01\x02" * 5000 + b"\x07"  # odd byte at the end must be dropped
    rec = _make_takes(lib, [a, b])
    assert recorder.finalize(rec) == "ready"
    out = subprocess.run(ffmpeg.decode_cmd(rec.audio_path, RATE), capture_output=True, check=True).stdout
    assert out == a + b[:-1]


def test_verification_failure_keeps_takes(lib, monkeypatch):
    rec = _make_takes(lib, [b"\x00\x01" * 8000])

    def broken(*a, **k):
        raise ffmpeg.FFmpegError("FLAC verification mismatch")

    monkeypatch.setattr(ffmpeg, "encode_flac_verified", broken)
    assert recorder.finalize(rec) == "failed"
    rec.reload()
    assert rec.meta.state == NEEDS_FINALIZE and "mismatch" in rec.meta.error
    assert recorder.take_files(rec) and not (rec.folder / "audio.flac").exists()
    monkeypatch.undo()
    assert recorder.finalize(rec) == "ready" and rec.reload().meta.state == READY


def test_empty_recording_is_discarded(lib):
    rec = _make_takes(lib, [b"", b"\x05"])
    assert recorder.finalize(rec) == "empty"
    assert not rec.folder.exists()


def test_refuses_to_start_on_low_disk(lib, monkeypatch):
    monkeypatch.setattr(recorder, "free_bytes", lambda p: 500_000_000)
    with pytest.raises(recorder.RecorderError, match="at least 1 GB"):
        recorder.start(lib, rate=RATE)
    assert lib.all() == []


def test_supervisor_killed_capture_adopted(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(1.5)
    old = s.supervisor_pid
    os.kill(old, signal.SIGKILL)
    assert wait_for(lambda: not s.alive())
    capture_pid = recorder.load_session(s.rec)["takes"][-1]["pid"]
    assert recorder._alive(capture_pid), "capture must survive the supervisor"
    actions = dict(recorder.recover_all(lib))
    assert actions[s.rec.id] == "adopted"
    assert s.alive() and s.supervisor_pid != old
    time.sleep(1.0)
    t_stop = time.monotonic()
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    assert any("Recorder restarted" in g["cause"] for g in m.gaps)
    assert 2.0 < m.duration < 3.2  # continuous: nothing lost while no supervisor was running
    assert len(recorder.load_session(s.rec) or {}) == 0  # takes dir removed with session


def test_everything_killed_then_recovered(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(2.0)
    info = recorder.load_session(s.rec)
    os.kill(info["supervisor_pid"], signal.SIGKILL)
    os.kill(info["takes"][-1]["pid"], signal.SIGKILL)
    assert wait_for(lambda: not s.alive() and not recorder._alive(info["takes"][-1]["pid"]))
    assert dict(recorder.recover_all(lib))[s.rec.id] == "finalized"
    m = s.rec.reload().meta
    assert m.state == READY and m.recovered and 1.5 < m.duration < 2.5


def test_recording_state_without_takes_is_cleaned(lib):
    rec = lib.create("crashed early", "recorded", state=RECORDING)
    assert dict(recorder.recover_all(lib))[rec.id] == "empty"
    assert not rec.folder.exists()


def test_live_recording_left_alone(lib):
    s = recorder.start(lib, rate=RATE)
    assert dict(recorder.recover_all(lib))[s.rec.id] == "live"
    s.stop(wait=20)


def test_failing_capture_backs_off_and_warns(lib, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "die:0")
    s = recorder.start(lib, rate=RATE)
    time.sleep(3.5)
    st = s.status()
    assert st.get("warning", "").startswith("No audio")
    info = recorder.load_session(s.rec)
    assert len(info["takes"]) <= 1  # empty failed takes are dropped, not accumulated
    assert len(list(s.rec.takes_dir.glob("take-*.raw"))) <= 1
    assert s.stop(wait=20) == "empty"

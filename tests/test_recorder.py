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
KILL = getattr(signal, "SIGKILL", signal.SIGTERM)
# These tests send POSIX signals (SIGKILL, SIGSTOP, the old SIGUSR controls) to the processes.
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX signals")


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
            os.kill(s.supervisor_pid, KILL)
        for t in (recorder.load_session(rec) or {}).get("takes", []):
            try:
                os.kill(t["pid"], KILL)
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

    with monkeypatch.context() as m:
        m.setattr(ffmpeg, "encode_flac_verified", broken)
        assert recorder.finalize(rec) == "failed"
    rec.reload()
    assert rec.meta.state == NEEDS_FINALIZE and "mismatch" in rec.meta.error
    assert recorder.take_files(rec) and not (rec.folder / "audio.flac").exists()
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


@posix_only
def test_supervisor_killed_capture_adopted(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(1.5)
    old = s.supervisor_pid
    os.kill(old, signal.SIGKILL)
    assert wait_for(lambda: not s.alive())
    capture_pid = recorder.load_session(s.rec)["takes"][-1]["pid"]
    assert recorder.pid_alive(capture_pid), "capture must survive the supervisor"
    actions = dict(recorder.recover_all(lib))
    assert actions[s.rec.id] == "adopted"
    assert s.alive() and s.supervisor_pid != old
    time.sleep(1.0)
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    assert any("Recorder restarted" in g["cause"] for g in m.gaps)
    assert 2.0 < m.duration < 3.2  # continuous: nothing lost while no supervisor was running
    assert len(recorder.load_session(s.rec) or {}) == 0  # takes dir removed with session


@posix_only
def test_everything_killed_then_recovered(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(2.0)
    info = recorder.load_session(s.rec)
    os.kill(info["supervisor_pid"], signal.SIGKILL)
    os.kill(info["takes"][-1]["pid"], signal.SIGKILL)
    assert wait_for(lambda: not s.alive() and not recorder.pid_alive(info["takes"][-1]["pid"]))
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


def test_disk_running_out_stops_cleanly(lib, monkeypatch):
    rec = _make_takes(lib, [b"\x00\x01" * 48000])  # 6 s at 16 kHz in the takes
    sup = recorder.Supervisor(lib, rec)
    sup.session = recorder.load_session(rec)
    # Plenty of space: keep going, no warning.
    monkeypatch.setattr(recorder, "free_bytes", lambda p: 50_000_000_000)
    assert sup._check_disk() and sup.warning is None
    # Under ten minutes left: warn but continue.
    monkeypatch.setattr(recorder, "free_bytes", lambda p: recorder.DISK_MARGIN + 5 * 60 * RATE * 2)
    assert sup._check_disk() and "minutes of recording left" in sup.warning
    # Not enough left to finalize safely: stop, and say why in the recording's notes.
    monkeypatch.setattr(recorder, "free_bytes", lambda p: 1000)
    assert sup._check_disk() is False
    assert any("Disk almost full" in e["cause"] for e in recorder.load_session(rec)["events"])
    assert recorder.finalize(rec) == "ready"


def test_commands_are_files_and_none_is_lost(lib):
    s = recorder.start(lib, rate=RATE)
    # Two quick commands in a row: both are applied in order (a single file would keep one).
    recorder.send_command(s.rec, "pause")
    recorder.send_command(s.rec, "resume")
    assert wait_for(lambda: len([g for g in (recorder.load_session(s.rec) or {}).get("events", [])
                                 if g["kind"] == "pause"]) == 1)
    assert s.status()["state"] == recorder.S_RECORDING
    assert not list((s.rec.takes_dir / recorder.COMMANDS).iterdir())  # consumed
    assert s.stop(wait=20) == "ready"


@posix_only
def test_signals_still_control_the_supervisor(lib):
    s = recorder.start(lib, rate=RATE)
    os.kill(s.supervisor_pid, signal.SIGUSR1)
    assert wait_for(lambda: s.status()["state"] == recorder.S_PAUSED)
    os.kill(s.supervisor_pid, signal.SIGUSR2)
    assert wait_for(lambda: s.status()["state"] == recorder.S_RECORDING)
    os.kill(s.supervisor_pid, signal.SIGTERM)
    assert wait_for(lambda: s.rec.reload().meta.state == READY, 20)


def test_liveness_needs_the_token_and_a_fresh_heartbeat(lib):
    s = recorder.start(lib, rate=RATE)
    assert s.alive() and s.info()["token"] == recorder.read_status(s.rec)["token"]
    # A status file from some other supervisor (another token) does not count.
    info = recorder.load_session(s.rec)
    from echo_app.fsutil import atomic_write_json

    atomic_write_json(recorder.session_path(s.rec), {**info, "token": "someone-else"})
    assert not s.alive()
    atomic_write_json(recorder.session_path(s.rec), info)
    assert wait_for(s.alive)
    s.stop(wait=20)


@posix_only
def test_hung_supervisor_is_left_alone(lib, monkeypatch):
    s = recorder.start(lib, rate=RATE)
    pid = s.supervisor_pid
    os.kill(pid, signal.SIGSTOP)
    try:
        assert wait_for(lambda: not s.alive(), timeout=recorder.HEARTBEAT_STALE + 2)
        assert s.hung()
        assert dict(recorder.recover_all(lib))[s.rec.id] == "live"  # within the grace period
        monkeypatch.setattr(recorder, "HUNG_GRACE", recorder.HEARTBEAT_STALE + 0.5)
        assert wait_for(lambda: not s.hung(), timeout=3)
        # Past the grace period it still holds the lock: recovery must not touch its takes.
        assert dict(recorder.recover_all(lib))[s.rec.id] == "hung"
        assert recorder.take_files(s.rec) and s.rec.reload().meta.state == RECORDING
    finally:
        os.kill(pid, signal.SIGCONT)
    assert wait_for(s.alive)
    assert s.stop(wait=20) == "ready"


@posix_only
def test_recording_from_the_previous_version_is_still_controlled(lib):
    """A session without a token (started before the upgrade) is recognized by its heartbeat
    and stopped with a signal."""
    s = recorder.start(lib, rate=RATE)
    time.sleep(1.0)  # some audio, so the stopped recording is kept rather than discarded as empty
    sent = []
    real_kill = os.kill

    def kill(pid, sig):
        sent.append(sig)
        real_kill(pid, sig)

    info = recorder.load_session(s.rec)
    del info["token"]
    from echo_app.fsutil import atomic_write_json

    atomic_write_json(recorder.session_path(s.rec), info)
    assert s.legacy and s.alive()
    import unittest.mock

    with unittest.mock.patch.object(recorder.os, "kill", kill):
        s.stop()
    assert [x for x in sent if x] == [signal.SIGTERM]  # kill(pid, 0) are liveness checks
    assert wait_for(lambda: s.rec.reload().meta.state == READY, 20)


def test_markers_follow_captured_audio_across_pauses(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(1.0)
    s.mark()
    s.pause()
    assert wait_for(lambda: s.status()["state"] == recorder.S_PAUSED)
    time.sleep(1.5)  # paused time is not audio: the next marker must not include it
    s.resume()
    assert wait_for(lambda: s.status()["state"] == recorder.S_RECORDING)
    time.sleep(0.5)
    s.mark("decisión sobre el precio")
    s.mark()
    s.note("la segunda nota")
    assert wait_for(lambda: len(s.markers()) == 3)
    assert s.markers()[2]["note"] == "la segunda nota"
    time.sleep(0.3)
    assert s.stop(wait=20) == "ready"
    m = s.rec.reload().meta
    ats = [mk["at"] for mk in m.markers]
    assert [mk["note"] for mk in m.markers] == ["", "decisión sobre el precio", "la segunda nota"]
    assert 0.8 < ats[0] < 1.3
    assert 1.3 < ats[1] < 2.0, ats  # about 1.0 + 0.5 s of audio, not 3 s of wall time
    assert ats == sorted(ats) and m.duration > ats[-1]


@posix_only
def test_markers_survive_a_crash(lib):
    s = recorder.start(lib, rate=RATE)
    time.sleep(1.0)
    s.mark("antes del corte")
    assert wait_for(lambda: s.markers())
    info = recorder.load_session(s.rec)
    os.kill(info["supervisor_pid"], signal.SIGKILL)
    os.kill(info["takes"][-1]["pid"], signal.SIGKILL)
    assert wait_for(lambda: not s.alive() and not recorder.pid_alive(info["takes"][-1]["pid"]))
    assert dict(recorder.recover_all(lib))[s.rec.id] == "finalized"
    assert [mk["note"] for mk in s.rec.reload().meta.markers] == ["antes del corte"]


def test_cli_mark_and_markers(lib, capsys):
    from echo_app import cli, settings

    settings.save(settings.Settings(data_dir=str(lib.data_dir), sample_rate=RATE))
    assert cli.main(["mark"]) == 1  # not recording
    s = recorder.start(lib, rate=RATE)
    time.sleep(0.6)
    assert cli.main(["mark", "--note", "aquí"]) == 0
    assert wait_for(lambda: s.markers())
    time.sleep(0.3)
    s.stop(wait=20)
    capsys.readouterr()
    assert cli.main(["markers", s.rec.id]) == 0
    assert "aquí" in capsys.readouterr().out
    assert cli.main(["list"]) == 0
    assert "[1 marker]" in capsys.readouterr().out

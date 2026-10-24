"""Recording through PortAudio for real. Opt-in: ECHO_PORTAUDIO_TESTS=1 (records the default input)."""

import os
import signal
import time

import pytest

from echo_app import recorder
from echo_app.library import READY, Library

pytestmark = pytest.mark.skipif(os.environ.get("ECHO_PORTAUDIO_TESTS") != "1",
                                reason="set ECHO_PORTAUDIO_TESTS=1 to record through PortAudio")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    from echo_app.audio import backend

    monkeypatch.setenv("ECHO_AUDIO_BACKEND", "portaudio")
    monkeypatch.setenv("ECHO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(backend, "_backend", None)
    return Library(tmp_path / "data")


def test_record_pause_stop(lib):
    s = recorder.start(lib, rate=48000)
    time.sleep(1.5)
    s.pause()
    time.sleep(0.7)
    s.resume()
    time.sleep(1.5)
    assert s.stop(wait=30) == "ready"
    m = s.rec.reload().meta
    assert m.state == READY and 2.5 < m.duration < 3.6, m.duration
    assert [g["kind"] for g in m.gaps] == ["pause"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
def test_supervisor_killed_then_recovered(lib):
    s = recorder.start(lib, rate=48000)
    time.sleep(2.0)
    os.kill(s.supervisor_pid, signal.SIGKILL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and s.alive():
        time.sleep(0.1)
    time.sleep(recorder.CAPTURE_GROWING + 0.5)
    # The capture ran inside the supervisor and died with it: the takes are finalized, not adopted.
    assert dict(recorder.recover_all(lib))[s.rec.id] == "finalized"
    m = s.rec.reload().meta
    assert m.state == READY and m.recovered and 1.0 < m.duration < 2.5

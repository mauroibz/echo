"""Kill-and-recover against real PipeWire. Opt-in: ECHO_PIPEWIRE_TESTS=1 (records the default input)."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

from echo_app import recorder, selfcmd
from echo_app.library import READY, Library

pytestmark = pytest.mark.skipif(
    os.environ.get("ECHO_PIPEWIRE_TESTS") != "1" or not shutil.which("pw-record"),
    reason="set ECHO_PIPEWIRE_TESTS=1 to run against real PipeWire")


def test_kill_everything_but_capture_then_recover(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("ECHO_DATA_DIR", str(data))
    lib = Library(data)
    cli = subprocess.Popen(selfcmd.command("record", "--wait", "--title", "kill test"), env=selfcmd.env(),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    t0 = time.monotonic()
    deadline = t0 + 10
    sess = None
    while time.monotonic() < deadline and sess is None:
        sess = recorder.active(lib)
        time.sleep(0.05)
    assert sess, "recording did not start"
    t_start = time.monotonic()
    time.sleep(3)
    # Kill the CLI and the supervisor without any chance to clean up.
    os.kill(cli.pid, signal.SIGKILL)
    os.kill(sess.supervisor_pid, signal.SIGKILL)
    cli.wait()
    take = sess.rec.takes_dir / recorder.load_session(sess.rec)["takes"][-1]["file"]
    size1 = take.stat().st_size
    time.sleep(2)
    assert take.stat().st_size > size1 + 48000 * 2, "capture must keep writing with no supervisor"
    assert dict(recorder.recover_all(lib))[sess.rec.id] == "adopted"
    time.sleep(2)
    t_stop = time.monotonic()
    assert sess.stop(wait=60) == "ready"
    m = sess.rec.reload().meta
    wall = t_stop - t_start
    assert m.state == READY
    assert abs(m.duration - wall) < 1.0, (m.duration, wall)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(sess.rec.audio_path)], capture_output=True, text=True).stdout
    assert abs(float(probe) - m.duration) < 0.05

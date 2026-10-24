"""File locks: exclusive across processes, released on close or exit, payload readable while held."""

import subprocess
import sys
import time

from echo_app import locks

HOLD = """
import sys, time
sys.path.insert(0, {src!r})
from echo_app import locks
lock = locks.acquire({path!r})
lock.write_payload('{{"pid": 1}}')
print("held", flush=True)
time.sleep(30)
"""


def _holder(tmp_path, path):
    src = str(__import__("pathlib").Path(locks.__file__).parents[1])
    p = subprocess.Popen([sys.executable, "-c", HOLD.format(src=src, path=str(path))], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def test_exclusive_between_processes_and_released_when_the_holder_dies(tmp_path):
    path = tmp_path / "x.lock"
    p = _holder(tmp_path, path)
    try:
        assert locks.acquire(path) is None
        assert locks.holder_payload(path) == '{"pid": 1}'  # readable while held
        t0 = time.monotonic()
        assert locks.acquire(path, wait=0.3) is None
        assert time.monotonic() - t0 >= 0.3
    finally:
        p.kill()
        p.wait()
    lock = locks.acquire(path)
    assert lock is not None
    lock.close()
    assert locks.holder_payload(path) is None


def test_close_releases(tmp_path):
    path = tmp_path / "y.lock"
    with locks.acquire(path) as lock:
        lock.write_payload("a")
        lock.write_payload("bc")
    assert path.read_text() == "bc"
    again = locks.acquire(path)
    assert again is not None
    again.close()

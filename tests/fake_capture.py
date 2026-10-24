"""Stand-in for pw-record in tests: writes a known PCM pattern at real-time speed.

Usage: fake_capture.py PATH BYTES_PER_SECOND
FAKE_MODE env: "" (normal), "die:<sec>" (exit abruptly), "stall:<sec>" (stop writing, stay alive)
Each take writes 16-bit samples counting up from FAKE_START (default 0), so content is checkable.
"""

import os
import signal
import struct
import sys
import time

path, bps = sys.argv[1], int(sys.argv[2])
mode = os.environ.get("FAKE_MODE", "")
marker = os.environ.get("FAKE_MODE_ONCE")  # file: apply mode only if marker does not exist yet
if marker:
    if os.path.exists(marker):
        mode = ""
    else:
        open(marker, "w").close()
kind, _, arg = mode.partition(":")
limit = float(arg) if arg else None

stop = False


def on_int(*_):
    global stop
    stop = True


signal.signal(signal.SIGINT, on_int)
if hasattr(signal, "SIGBREAK"):  # Windows: the recorder stops a capture with a console break
    signal.signal(signal.SIGBREAK, on_int)
chunk_frames = bps // 2 // 20  # 50 ms chunks (mono assumption is fine for tests)
counter = 0
start = time.monotonic()
fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
n = 0
while not stop:
    elapsed = time.monotonic() - start
    if limit is not None and elapsed >= limit:
        if kind == "die":
            os._exit(1)
        if kind == "stall":
            time.sleep(0.05)
            continue
    data = struct.pack(f"<{chunk_frames}h", *[(counter + i) % 32768 for i in range(chunk_frames)])
    counter += chunk_frames
    os.write(fd, data)
    n += 1
    target = start + n * 0.05
    time.sleep(max(0.0, target - time.monotonic()))
os.close(fd)

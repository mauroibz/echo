# Design

## Decisions

### Command file instead of signals

`recordings/<id>/command` holds one word: `pause`, `resume` or `stop`, written atomically by
the window or CLI. The supervisor's loop already wakes twice a second for the heartbeat; it
reads and deletes the file there. Latency is at most half a second, within the existing
"stop within a second" behavior. On POSIX the old signal handlers stay for one release and
write the same flag, so a recording started before the upgrade can still be stopped.

### Liveness

`session.json` gains `token` (random) and `started`. A supervisor is alive if its pid exists
and `status.json` was updated within 3 seconds; `recover` treats a stale heartbeat with a live
pid as hung and handles it as today's "dead supervisor" case after a 10-second grace. Capture
liveness: the backend's process handle while in the same process; for recovery after a crash,
the take file growing within 3 seconds.

### Locks

`locks.try_lock(path) -> handle | None` and `handle.close()`. POSIX: `fcntl.flock`. Windows:
`msvcrt.locking` on the first byte with `LK_NBLCK`. Lock files keep their JSON payloads.

### Backend interface

```python
class CaptureBackend(Protocol):
    def list_sources(self) -> list[Source]: ...
    def default_source(self) -> Source | None: ...
    def start_capture(self, source, rate, channels, path) -> Capture: ...  # writes raw s16
    def meter(self, source) -> Meter: ...  # low-rate stream for the level meter
    def player(self, rate, channels) -> Output: ...  # raw s16 sink for playback

class Capture(Protocol):
    pid: int | None
    def alive(self) -> bool: ...
    def stop(self, timeout) -> None: ...  # flush, then escalate
```

`audio.backend.get()` returns the PipeWire backend when `pw-record` exists, else raises with
the doctor message, until the next change adds PortAudio. `tests/fake_capture.py` implements
the protocol so recorder tests do not touch audio.

## Decisions made while implementing

- **A folder of command files, not one file.** `takes/commands/<time_ns>-<rand>.cmd`, each
  written atomically and holding `{"command": "pause"}`; the supervisor reads them oldest
  first and deletes each. A single overwritten file would lose one of two quick commands (a
  marker and its note, or pause then resume). Living in `takes/`, they disappear with the
  takes when the recording is finalized.
- **Tick 0.1 s** instead of 0.25 s, so pause and stop take effect as quickly as the signals
  did (the pause-and-resume test measured 0.25 s more audio with the longer tick).
- **Heartbeat during finalize.** A thread keeps writing `status.json` while the takes are
  encoded and verified, which takes about a minute for two hours of audio; without it, a stale
  heartbeat would let recovery finalize the same takes in parallel.
- **Hung supervisor.** Alive: heartbeat under 3 s, matching token, process exists. Within 10 s
  of a stale heartbeat recovery reports "live" and waits; after that, if the process still
  exists and the recording lock is taken, recovery reports "hung" and leaves the takes alone
  (only our supervisor takes that lock); otherwise it adopts or finalizes as before.
- **Capture liveness after a crash**: the capture's pid exists and its take was written within
  3 s (pw-record writes every 20 ms), checked through the file's mtime, which needs no waiting.
- **Upgrade path.** A session without a token was started by the previous version: it is
  recognized by its fresh heartbeat alone and controlled with signals.
- **Zombies.** `pid_alive` reaps an exited child with `waitpid(WNOHANG)` (the window spawns the
  supervisor and never waits for it), replacing the `/proc/<pid>/stat` check.
- **Backend objects** look like processes (`pid`, `alive`, `stop`; `poll`, `terminate`,
  `wait` for outputs), so `Playback` still pipes ffmpeg straight into the output process. The
  test capture is a `CommandBackend` selected by `ECHO_CAPTURE_CMD`, still running
  `tests/fake_capture.py` as a process, so the recorder tests exercise real child processes.
- **Windows locks** take one byte at offset 2^30, past the end of the file, so the worker's
  JSON payload at the start stays readable to other processes while the lock is held.
- **1.5 verification**: the PipeWire kill-and-recover integration test passes. The two-hour
  recording is made from the computer's output ("Computer audio") rather than the microphone,
  so no room audio is captured while nobody is there; it exercises the same `pw-record`
  pipeline, takes, pause and finalize.
- **1.5 results**: the PipeWire kill-and-recover integration test passes; the two-hour recording
  through real PipeWire (40 minutes, a 2-minute pause, 80 minutes, controlled with `echo-app
  pause`, `resume` and `stop`, i.e. command files) produced a verified FLAC of 7200.02 s, with
  the pause noted at 2400.15 s lasting 120.15 s, no takes left, and stop to saved in 2 s. The
  source was the computer's output, which was silent, so FLAC encoding was faster than it would
  be for speech.

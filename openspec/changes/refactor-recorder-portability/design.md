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

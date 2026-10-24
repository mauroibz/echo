# Design

## Context

Measured on the target machine: `pw-record --raw` writes headerless PCM in about 4 KB blocks
(~10 writes per second at 48 kHz mono s16), closes cleanly on SIGINT, and after SIGKILL every
byte already written is readable. Targeting a sink node with `stream.capture.sink=true`
records what the computer plays. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- The window can crash, the recorder can crash, or both, without losing captured audio.
- Stdlib-only recorder code so the recorder process starts fast and has no third-party risk.

**Non-Goals:**
- Recording several sources at once into separate tracks.
- Audio processing (noise reduction, gain). EasyEffects already provides that as a source.

## Decisions

### Three processes, each able to die alone

```
 UI (Qt) ──signals/status files──> recorder supervisor ──spawns──> pw-record
                                   (echo-app _recorder <id>)        (raw PCM → takes/take-NNN.raw)
```

- **pw-record** writes raw PCM. It runs in its own session, so killing the supervisor or the
  UI does not kill it.
- **Supervisor** (`echo-app _recorder <id>`, also its own session) owns the lifecycle: starts
  takes, flushes (`fsync`) the active take and the takes directory every 2 s, detects death
  and stalls, restarts capture, finalizes on stop. It writes `session.json` (fsync'd, on every
  state change) and `status.json` (best-effort heartbeat every 0.5 s).
- **UI or CLI** controls the supervisor with signals: SIGUSR1 pause, SIGUSR2 resume, SIGTERM
  stop. It reads `status.json` for state and the tail of the active take for the level meter,
  so no second capture stream is needed while recording.

Alternatives considered: capturing inside the Qt process with QAudioSource (rejected: a UI
crash loses the buffer and stops capture); a systemd user service (rejected: extra install
surface and harder to reason about than a detached child).

### Raw takes, FLAC after verification

Each start or resume opens `takes/take-NNN.raw` with `take-NNN.json` (format, start time).
Raw PCM has no header to corrupt, and takes are concatenated by byte order. On stop:
1. Truncate each take to whole frames.
2. Stream all takes through `ffmpeg` to `audio.flac.partial`, hashing the PCM on the way in.
3. Decode the FLAC back to PCM, hash it, compare hashes and sample counts.
4. Rename to `audio.flac`, fsync, update `meta.json` (state ready, duration, gaps), and only
   then delete `takes/`.
Any failure leaves the takes and sets state `needs_finalize` with the error.

### Recovery

Run at the start of the GUI and of CLI commands that touch the library. For each recording
folder with `takes/`:
- supervisor pid alive and its `/proc/<pid>/cmdline` matches → live, nothing to do;
- supervisor dead, capture pid alive and matching → start a new supervisor in adopt mode
  that watches the orphaned capture and continues as normal;
- nothing alive → finalize, marking `recovered: true`.
Matching on cmdline (not only pid) prevents acting on a recycled pid.

### Interruptions

The supervisor checks every 250 ms and wakes immediately on control signals (a
`signal.set_wakeup_fd` pipe). Capture exiting without being asked, or the file not growing
for 3 s, closes the take, records an event `{at, wall, cause, kind}` and starts a new take.
A capture that fails before producing any audio is retried with exponential backoff
(0.5 s up to 5 s), its empty take is dropped, and the status shows "No audio from the input";
after three such failures on a non-default source it switches to the default and notes it.

Measured PipeWire behavior shapes this: with no extra stream flags, a missing target makes
pw-record fall back to the default input, and a running stream whose device disappears is
moved to the default by the session manager. Audio therefore continues on unplug; the
supervisor checks every 5 s whether the chosen source still exists and records the switch.

### Levels and listening

- While recording: the UI reads the last 50 ms of the active take (peak dBFS, clip flag).
- While idle: a monitor `pw-record ... -` at 16 kHz to stdout, read by the UI.
- Listening: `pw-loopback -C <source>` started and stopped with the toggle.

### Format

48 kHz, s16, mono by default (settings allow stereo). 5.5 MB/min raw, ~3 MB/min as FLAC.

## Risks / Trade-offs

- [SIGKILL of the capture process itself] → pw-record buffers up to 4 KB in user space,
  so a SIGKILL of pw-record (not of the supervisor or UI) can lose its last ~40 ms. SIGINT and
  SIGTERM flush fully. Killing the supervisor or UI loses nothing. Measured on the target machine.

- [pw-record changes behavior in a future PipeWire] → doctor checks it exists; the engine's
  integration test runs against the real tool; the recorder command is isolated in one function.
- [fsync every 2 s on slow disks] → cost is tiny at 96 KB/s.
- [Signals are not delivered while the supervisor is busy finalizing] → stop is idempotent; the
  UI shows "finalizing" from `status.json`.

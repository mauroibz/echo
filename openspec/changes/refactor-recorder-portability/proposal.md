# Proposal

## Why

The recorder and the worker rely on Linux-only mechanisms that are incidental to what they do:
POSIX signals for pause, resume and stop; `/proc` to recognize a live supervisor; `fcntl`
locks; and `pw-record` as the only way to capture. Each has a portable equivalent that is also
simpler to test. Doing this on Linux first, with no behavior change, is what makes a Windows
port (and Ubuntu 22.04 with PulseAudio) a bounded piece of work instead of a rewrite.

## What Changes

- Pause, resume and stop become a `command` file in the recording folder that the supervisor
  polls, alongside the `status.json` it already writes. Signals remain accepted on POSIX for
  one release so a running recording survives the upgrade.
- Supervisor and capture liveness come from a start token in `session.json`, the pid, and the
  heartbeat already in `status.json`, not from `/proc/<pid>/cmdline`.
- One `locks.py` with `fcntl` on POSIX and `msvcrt` on Windows, used by the three call sites.
- A capture backend interface (`start(target, path) -> process-like`, `flush_and_stop()`,
  `list_sources()`, `meter_stream()`) with the PipeWire implementation moved behind it. The
  PipeWire backend stays the only one in this change and stays the default on Linux.
- Playback output and the idle meter go through the same backend module.

## Capabilities

### Modified Capabilities
- `audio-capture`: same requirements; the mechanism for control and liveness changes.

## Impact

`recorder.py`, `cli_rec.py`, `fsutil.py`, `transcription.py`, new `locks.py`,
`audio/backend.py` with `audio/pipewire.py` behind it, `tests/test_recorder.py`,
`tests/fake_capture.py`. No user-visible change; the measured guarantees in `docs/design.md`
(SIGINT flush of `pw-record`, 40 ms loss bound) are preserved because the PipeWire backend
still stops `pw-record` with SIGINT.

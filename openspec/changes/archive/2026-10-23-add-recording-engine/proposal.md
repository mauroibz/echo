# Proposal

## Why

Recording is the part of Echo where a failure is unrecoverable: a lost stretch of a long
stream-of-consciousness recording cannot be redone. The recorder has to keep every sample
that reached the machine even if the window crashes, the recorder is killed, the input
device disappears, or power is cut.

## What Changes

- List capture sources: microphones, virtual sources, and "what the computer is playing"
  (output monitors), with the system default preselected.
- Live input level for the selected source before and during recording; optional listening
  to the input through the current output.
- Record, pause, resume and stop, running in a background recorder process that does not
  depend on the window.
- Continuous crash-safe storage: raw takes flushed to disk every two seconds, finalized into a
  lossless FLAC only after the encoded audio is verified bit-identical.
- Automatic recovery on next start: re-attach to a recording still running, or finalize one
  whose recorder died.
- Device loss handling: retry, then fall back to the default input, logging the gap.
- CLI: `echo-app record`, `pause`, `resume`, `stop`, `status`, `sources`, `recover`.

## Capabilities

### New Capabilities
- `audio-capture`: capture sources, level monitoring, the recording lifecycle, durability
  guarantees, and crash recovery.

### Modified Capabilities

## Impact

New modules under `src/echo_app/audio/`. Uses PipeWire's `pw-record`, `pw-dump`,
`pw-loopback` and `ffmpeg` as subprocesses. Recording folders gain a `takes/` directory and
`session.json` while recording.

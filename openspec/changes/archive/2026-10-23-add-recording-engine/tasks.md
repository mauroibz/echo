# Tasks

## 1. Sources and levels

- [x] 1.1 Implement source discovery from `pw-dump` (inputs, virtual sources, output monitors, default source) and `echo-app sources`; verify with unit tests on captured pw-dump JSON and by running the command
- [x] 1.2 Implement PCM level computation (peak dBFS, clip) and the idle monitor stream; verify unit tests on synthetic PCM and a manual check that the level moves with the mic
- [x] 1.3 Implement listening through `pw-loopback` start/stop; verify the loopback node appears and disappears in `pw-dump`

## 2. Recorder supervisor

- [x] 2.1 Implement session/status files and take management (start, pause, resume, stop) with periodic fsync; verify with an integration test using a fake capture command
- [x] 2.2 Implement interruption handling (unexpected exit, stall, fallback to default) with gap notes; verify with tests where the fake capture dies and stalls
- [x] 2.3 Implement verified finalize (frame truncation, FLAC encode, decode-hash compare, atomic rename, takes removal) and empty-recording discard; verify with tests including a forced verification failure that keeps takes
- [x] 2.4 Implement disk-space guard at start and during recording; verify with a test that stubs free space

## 3. Recovery and CLI

- [x] 3.1 Implement recovery (live, adopt orphaned capture, finalize dead) with cmdline matching; verify with tests that SIGKILL the supervisor, and both supervisor and capture
- [x] 3.2 Add CLI commands `record` (with `--wait`), `pause`, `resume`, `stop`, `status`, `sources`, `recover`, `finalize`; verify with an end-to-end run against real PipeWire
- [x] 3.3 Run the kill-and-recover test against real PipeWire: record, SIGKILL the CLI and supervisor, confirm capture continues, recover, stop, and confirm the FLAC duration matches wall-clock capture time within 1 s

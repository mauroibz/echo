# Tasks

- [x] 1.1 Synthetic two-channel calls (the user through a gate on one track, two or three people on the other) and the measurements in design.md; a real call transcribed with each method
- [x] 1.2 `speakers.track_turns`, `split_spans`, `interrupting_sides`, `tracks_differ`; tests
- [x] 1.3 The worker cuts calls by track and by segmentation of the computer audio, from a second; copied tracks are one microphone; tests
- [x] 1.4 The computer-audio capture has its own application and node name; test
- [x] 1.5 README, `docs/design.md`, CHANGELOG
- [ ] 1.6 Record a call with the fix and check both tracks differ (needs a person: a real call)

## Blocked

- **1.6** needs a real call. With the noise gate on the microphone as usual, record a short call
  with "Computer audio" on and run `echo-app info ID --json`; then transcribe it: the log should
  not say "both tracks hold the same sound", and the user's passages should be speaker 1. In
  `pw-dump` during the recording the capture named "Echo computer audio" should be linked to the
  default output's monitor.

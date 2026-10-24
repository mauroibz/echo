# Tasks

- [ ] 1.1 Supervisor: `mark` command through the command file, time computed from bytes captured so pauses and gaps are honored, appended to `session.json` and merged into `meta.json` on finalize; recover keeps markers; tests (needs hardware: a microphone for the final real-recording check only; the rest is testable with the fake backend)
- [ ] 1.2 `echo-app mark [--note]`; `M` in the window while recording; tray item; a one-line note field that appears after marking and closes on Enter or after 10 s
- [ ] 1.3 Waveform: draw markers, hover notes, drag, remove, add at playhead; next/previous shortcuts; UI tests
- [ ] 1.4 Transcript margin anchors at the passage containing each marker; click to play from there

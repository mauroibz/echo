# Tasks

- [x] 1.1 `locks.py` with POSIX and Windows implementations; switch `fsutil`, `transcription`, `recorder`; tests
- [x] 1.2 Command file: writer in `recorder.py` client side, reader in the supervisor loop; keep signal handlers writing the same flags; tests for pause/resume/stop through the file
- [x] 1.3 Liveness from `session.json` token, pid and heartbeat; remove `/proc` reads; recovery tests for live, hung and dead supervisors
- [x] 1.4 `audio/backend.py` protocol; move PipeWire capture, meter and `pw-play` output behind it; `fake_capture.py` implements the protocol
- [x] 1.5 Run the PipeWire integration test and a real two-hour recording with pause and resume; confirm `docs/design.md` guarantees still hold (needs hardware: PipeWire and a microphone)

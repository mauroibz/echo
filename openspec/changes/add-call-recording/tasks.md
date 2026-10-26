# Tasks

## 1. Capture

- [x] 1.1 `pipewire.DEFAULT_OUTPUT`, a monitor source with no target (captures the default output and follows it); `Backend.records_outputs` decides whether it is offered; tests on the `pw-record` command; a PipeWire integration test (under `ECHO_PIPEWIRE_TESTS`) that a tone played to the default output is captured
- [x] 1.2 Paired takes in the supervisor: `out-NNN.raw` next to `take-NNN.raw`, started and stopped together; either capture dying or stalling ends both and starts a new pair; a computer-audio capture that cannot start leaves the input recording with a warning and a note; the take entry in `session.json` carries `out` (file, pid); elapsed time stays the input's; tests with the fake capture (kill the out capture, stall it, pause and resume)
- [x] 1.3 Adoption and recovery of pairs: a supervisor killed with both captures alive adopts both; with the out capture dead, adopts the input and ends the out take; with everything dead, finalizes; tests for each
- [x] 1.4 Two-channel finalize: paired takes interleaved into the verified FLAC (input on channel 1, computer audio on channel 2); a pair the supervisor stopped together (`"align": "end"` in its take entry) is aligned at the end, any other at the start; a missing or empty out take is silence; `meta.json` gets `channels: 2` and `tracks: ["mic", "computer"]`; tests on content and alignment; measure interleaving an hour of audio and record the time

## 2. Listening and transcription

- [x] 2.1 Mixing on decode: `ffmpeg.decode_cmd(..., mix=True)` sums the two channels into one; the waveform and the worker use it for two-track recordings; playback plays the sum in both ears through the limiter; tests on the ffmpeg commands and on decoded content of a two-channel file
- [x] 2.2 Speakers per track: each passage goes to the louder track (RMS over the passage), passages are clustered per track, the microphone's speakers numbered first; tests with the stub embedder on a synthetic two-channel recording

## 3. Command line and settings

- [x] 3.1 `settings.computer_audio` (remembered, off by default); `echo-app record --computer-audio / --no-computer-audio`, defaulting to the setting; `recorder.start(computer_audio=...)` refuses it for a monitor source or a backend that cannot record outputs; `status` names both sources; `info` and `info --json` report `tracks`; tests in `tests/test_recorder.py` and `tests/test_agent_cli.py`

## 4. Window

- [x] 4.1 The toggle under the source (shown when the source is an input and the backend records outputs, disabled while recording), saved in settings; a second slim meter for the computer audio, from an idle monitor before recording and from the tail of the current out take while recording; offscreen tests: toggle shown and hidden by source, record with it on gives a two-channel recording, the second meter moves

## 5. Docs

- [x] 5.1 README (recording a call, headphones versus speakers, the two-channel file, the CLI flag), `docs/design.md` (paired takes, alignment and drift measurements, mixing, speakers per track), CHANGELOG, roadmap table

## 6. On a real call

- [ ] 6.1 Record a 10-minute Meet, Teams or Zoom call with headphones (needs hardware: a microphone and a real call): the call app works normally throughout; both sides are heard in playback; the transcript has both sides and the user is speaker 1
- [ ] 6.2 Switch the default output (for example to headphones) in the middle of a two-track recording (needs hardware: a second output device in use): the computer audio follows to the new output with no gap longer than two seconds

## Blocked

Both open tasks need a person, a microphone and a real call; everything else is done and tested
with the fake capture, and the default-output capture was checked against real PipeWire
(`ECHO_PIPEWIRE_TESTS=1 pytest tests/test_pipewire_integration.py`).

- **6.1** With headphones on, select the microphone, turn on "Computer audio", join a Meet,
  Teams or Zoom call with one other person, press Record and talk for about 10 minutes, then
  Stop. Look for: the call app's microphone and sound work normally the whole time; both meters
  move (the second one when the other person speaks); playback has both voices in both ears at
  similar levels; `echo-app info <id> --json` shows `"tracks": ["mic", "computer"]`; after
  transcription, your passages are speaker 1 and theirs speaker 2, with no passage of theirs
  given to you. Note any misattributed passages in `design.md`.
- **6.2** During a two-track recording, change the default output (plug or unplug headphones,
  or pick another output in the desktop's sound settings) while the other side is talking.
  Look for: the computer-audio meter keeps moving within two seconds, and the finished
  recording has the other side before and after the switch with no gap over two seconds.


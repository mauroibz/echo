# Proposal

## Why

Video calls (Meet, Teams, Zoom) are a main use of Echo, and today it records one source: the
microphone, which hears only the user (and the other side faintly, through speakers), or
"Computer audio", which hears only the other side. Recording a call means choosing which half to
lose, or screen-recording it in OBS and importing the video. PipeWire lets several programs read
the microphone and the output at once, so Echo can record both while the call app keeps using
them unchanged.

## What Changes

- **"Also record computer audio".** When the source is a microphone, a toggle under it adds what
  the computer plays (the default output, followed when it changes) as a second track. The call
  app is not affected: Echo only reads the microphone and a copy of the output.
- **Two tracks, one recording.** The microphone and the computer audio are captured by two
  processes, each with the existing guarantees (written continuously, flushed every 2 s,
  restarted after interruptions, adopted or finalized after a crash). On stop they become one
  verified, lossless FLAC with two channels: channel 1 the user's microphone, channel 2 the
  computer audio. The sides cannot be separated after mixing, so the file keeps them apart.
- **Heard and transcribed as one conversation.** Playback, the waveform and transcription mix the
  two channels. Audio export copies the two-channel file unchanged.
- **Who said what.** Speaker labels cluster each side on its own, so a voice from the microphone
  and a voice from the call are never merged, and the microphone's speakers come first.
- **Two meters** while the toggle is on, before and during recording: the microphone's (with its
  gain and silence hint, as now) and a second one for the computer audio.
- **Command line:** `echo-app record --computer-audio`; `echo-app info --json` reports the tracks.
- The window remembers the toggle; the README explains headphones versus speakers.

Out of scope: echo cancellation of the microphone (with speakers, the microphone also hears the
call; headphones avoid it), choosing a specific output instead of the default, more than two
tracks, computer audio on backends that cannot record outputs (PortAudio; Windows loopback is
`add-windows-loopback`).

## Capabilities

### Modified Capabilities
- `audio-capture`: a second, simultaneous track of the computer audio; source selection,
  monitoring and the no-loss guarantees cover both tracks.
- `playback-and-crop`: two-track recordings play and draw as a mix; export keeps the tracks.
- `transcription`: two-track recordings are transcribed as a mix and speakers are found per side.
- `command-line`: `record --computer-audio`; tracks in `info --json`.
- `desktop-app`: the toggle and the second meter in the recording controls.

## Impact

`audio/pipewire.py` (the default output as a capture source), `audio/backend.py`,
`recorder.py` (paired takes, adoption and recovery of both, two-channel finalize),
`audio/ffmpeg.py` (interleaving paired takes into the verified FLAC, mixing on decode),
`audio/playback.py`, `audio/peaks.py`, `worker/service.py` (mixed decode, speakers per side),
`library.py` (`tracks` in `meta.json`), `settings.py`, `cli_rec.py`, `cli_json.py`,
`ui/recorder_panel.py`, `README.md`, `docs/design.md`, `CHANGELOG.md`. No new dependencies.

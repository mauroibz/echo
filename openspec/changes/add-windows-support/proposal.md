# Proposal

## Why

Echo is Linux only. Windows is where most people who would want it are. After
`refactor-recorder-portability`, what remains is one audio backend, a paths and trash module,
an installer, and a test run on Windows. Decision taken: ship Windows with microphone
recording first; "computer audio" (loopback) follows in its own change once verified.

## What Changes

- A PortAudio capture backend through `sounddevice` (prebuilt wheels on every OS): source
  listing, capture to raw PCM inside the supervisor process with the same 2-second fsync, a
  low-rate meter stream, and playback output. Used on Windows and macOS, and on Linux when
  PipeWire has no audio nodes.
- `paths.py` maps the five folders to `%APPDATA%`, `%LOCALAPPDATA%` and the user's Documents
  folder on Windows; `send2trash` replaces the freedesktop trash code on every OS.
- `install.ps1` and `uninstall.ps1`: install uv and ffmpeg with winget if missing, `uv sync`
  the chosen profile, create a Start Menu shortcut running `pythonw`, register `.flac`,
  `.opus`, `.m4a` "Open with Echo". `doctor` gains Windows wording and checks.
- The fast test suite runs on `windows-latest` in CI with the fake capture backend.

## Capabilities

### Modified Capabilities
- `installation`: Windows install and uninstall.
- `audio-capture`: a second capture backend; the "computer audio" source is Linux only until
  the follow-up change.

## Impact

New `audio/portaudio.py`, `install.ps1`, `uninstall.ps1`, `data/echo-app.ico`; changes in
`paths.py`, `library.py` (trash), `audio/playback.py`, `doctor.py`, `selfcmd.py` (`pythonw`
for detached children), README. Base profile gains `sounddevice` and `send2trash`.

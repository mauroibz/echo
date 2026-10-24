# Changelog

Notable changes to Echo. Versions are git tags (`vX.Y.Z`); `main` may be ahead of the latest
tag.

## Unreleased

### Added

- `echo-app doctor` names the install command for the running distribution (apt, dnf or
  pacman), detects a session where PulseAudio still owns audio, and checks the X11 cursor
  library the window needs.
- Continuous testing on Ubuntu and Fedora.

### Fixed

- `./install.sh` failed with Fedora's packaged `uv`, which turns automatic Python downloads
  off; it now installs the pinned Python explicitly.

## 0.1.0 - 2026-10-24

First public release: crash-safe recording from any PipeWire input or the computer's own
audio, import with WhatsApp date recognition and duplicate detection, local Spanish
transcription on an NVIDIA GPU, an autosaving editor with follow-along playback, full-text
search, non-destructive crop, and the Lagoon look in light and dark.

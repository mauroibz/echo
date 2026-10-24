# Changelog

Notable changes to Echo. Versions are git tags (`vX.Y.Z`); `main` may be ahead of the latest
tag.

## Unreleased

### Added

- `echo-app doctor` names the install command for the running distribution (apt, dnf or
  pacman), detects a session where PulseAudio still owns audio, and checks the X11 cursor
  library the window needs.
- Continuous testing on Ubuntu and Fedora.
- Transcription without an NVIDIA GPU: `./install.sh --with-transcription` now picks a build
  for an NVIDIA GPU, an AMD GPU (ROCm, untested) or the processor. On the processor Echo uses
  int8 weights and transcribes an hour of audio in about five minutes on a 6-core desktop.
  Echo says how long transcription takes on your computer once it has measured it.
- A dictionary of people and terms that learns from your corrections: fix a name once and a
  chip offers to add it; Echo then spells it right in new transcripts and fixes it in existing
  ones, underlining every automatic correction with one-click undo. An optional "who is
  speaking, what about" line per recording, `echo-app transcribe --context`, and Settings →
  Dictionary to tidy the list.
- Passage times: a margin with each passage's start time (Ctrl+T), "Copy with timestamps", and
  export to SRT and VTT subtitles and JSON, from the edited text too; `echo-app export`.
  Follow-along and Ctrl+click now work on edited transcripts.
- Markers: press M while recording (or use the tray, or `echo-app mark --note`) to mark a
  moment, with an optional note. They show on the waveform and beside the transcript, can be
  moved, edited and removed, and Alt+arrows jump between them.
- Transcription in 13 more languages besides Spanish (the transcript's menu, Settings, or
  `echo-app transcribe --language`); the Spanish adapter is used for Spanish only.
- Passages to check: Echo shades passages that came back short, needed a retry or that the
  model was unsure of, says why on hover and counts them. Passages the model was very unsure of
  are now retried, which recovers sentences a context sentence occasionally turned into a
  fragment.

### Fixed

- `./install.sh` failed with Fedora's packaged `uv`, which turns automatic Python downloads
  off; it now installs the pinned Python explicitly.

## 0.1.0 - 2026-10-24

First public release: crash-safe recording from any PipeWire input or the computer's own
audio, import with WhatsApp date recognition and duplicate detection, local Spanish
transcription on an NVIDIA GPU, an autosaving editor with follow-along playback, full-text
search, non-destructive crop, and the Lagoon look in light and dark.

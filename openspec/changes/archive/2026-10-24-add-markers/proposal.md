# Proposal

## Why

In a two-hour recording the hard part is finding the minute that mattered. The person
recording knows that moment when it happens. One key press then saves many minutes of
scrubbing later.

## What Changes

- While recording, `M` (and a tray menu item, and `echo-app mark [--note TEXT]`) adds a marker
  at the current time, with an optional short note typed afterwards without stopping.
- Markers are stored in `meta.json`, drawn on the waveform, listed as anchors in the transcript
  margin, and reachable with "next/previous marker" during playback.
- Markers can be added, moved and removed after recording by clicking the waveform.
- Export to Markdown turns markers into headings (see add-markdown-vault-export).

## Capabilities

### Modified Capabilities
- `audio-capture`: add a marker while recording.
- `playback-and-crop`: markers on the waveform and marker navigation.
- `transcript-editor`: markers as anchors.

## Impact

`recorder.py` (supervisor records marker times relative to captured audio, honoring pauses and
gaps), `library.py` (`markers` in `meta.json`), `ui/player.py`, `ui/transcript.py`,
`ui/recorder_panel.py`, `cli_rec.py`, export.

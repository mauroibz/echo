# Proposal

## Why

During a call or a class the window is in the way, and hiding it to the tray hides the
recording too: there is no time to glance at, no quick marker, no sign the microphone went
silent. A small dock that floats over other windows keeps what matters while recording and
nothing else. The approved canvas (2026-10-29, the Dock board) is the reference.

## What Changes

- **The dock:** a small pill that floats above other windows. At rest: the wordmark, the input's
  name, a Record button and a button back to the window. Recording: a pulsing dot, the time, a
  small wave that follows the level, what is recorded (microphone, computer audio), Marker with
  a count, Pause, Stop and back to the window. Paused: amber, the time blinking, the wave still.
  After Stop: "Saved", with transcription progress when it runs, Open and Done; it goes back to
  rest by itself.
- **Minimal:** while recording, after a few seconds without the pointer over it, the dock
  shrinks to the dot and the time; the pointer brings the rest back.
- **Problems** (a silent input, a recorder warning) show in the dock itself, in amber.
- **Getting there:** Ctrl+Shift+D (and View → Recording dock) swaps the window for the dock and
  back; closing the window while recording shows the dock instead of only the tray icon. The
  dock is dragged from anywhere on it and remembers where it was left.

## Capabilities

### Modified Capabilities
- `desktop-app`: closing during a recording shows the dock; added the dock.

## Impact

New `ui/record_dock.py`; `ui/main_window.py` (action, close, state); `ui/recorder_panel.py`
(marker without the note field, a count of markers); `docs/guide.md`, `docs/design.md`,
`CHANGELOG.md`. No new dependency.

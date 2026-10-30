# Proposal

## Why

`refine-window` made the window calm; what is left is that changes happen in a jump. The
recorder switches state between one frame and the next, a marker appears without a sign that it
was taken, a new recording pops into the list, Details snaps open, a message appears and
vanishes. Short, quiet motion where something changes tells the user what changed without
reading, and makes Echo feel finished. The approved canvas (2026-10-29, the Motion board) is the
reference.

## What Changes

- Recording: the coral block fades in when recording starts; the dot beside "RECORDING" pulses;
  paused, it turns amber and blinks slowly and the time dims.
- Markers: the marker button sends out a ring when pressed; a new marker drops onto the
  waveform with a small bounce.
- The list: a new recording slides in; a transcribing row has a light sweep along its progress
  bar while the work runs.
- Player: the play and pause icons cross in a short fade; following along, the transcript
  scrolls smoothly to the passage that is playing.
- Details opens and closes by sliding from the right; messages fade in and out.
- Reduce motion: a setting (Settings → Appearance), on by itself when the desktop has
  animations turned off (GNOME's "Animations", KDE's animation speed at instant). Then nothing
  moves except what carries information (the time, the level, progress).

Durations are 120 to 420 ms. Nothing animates while the window is hidden.

## Capabilities

### Modified Capabilities
- `desktop-app`: visual identity gains motion and reduce motion.

## Impact

New `ui/motion.py`; `ui/recorder_panel.py`, `ui/player.py`, `ui/library_view.py`,
`ui/main_window.py`, `ui/transcript.py`, `ui/dialogs.py` (setting), `settings.py`
(`reduce_motion`). No new dependency.

## Why

On first launch the level meter in the welcome screen stayed flat. The idle meter ran only
while the main window had focus, and the welcome dialog takes focus, so nothing was measured.
KDE on Wayland also does not always focus a window started from a terminal. Separately, an
input that sends exact digital silence (muted, unplugged or with the gain all the way down)
drew an empty bar that looked the same as a broken meter.

## What Changes

- The idle meter runs while the Echo window is shown, including under its own dialogs, and
  stops when the window is minimized or hidden to the tray.
- After four seconds of exact digital silence, before or during a recording, Echo shows a hint
  under the meter; the welcome screen shows the same hint.

## Impact

- `ui/recorder_panel.py`, `ui/main_window.py`, `ui/dialogs.py`, `tests/test_ui.py`, README
  troubleshooting.

## Why

The user records meetings from the dock so the window is out of the way, but had to bring the
window back to write a note, and to press Ctrl+Shift+D at every recording to get the dock.

## What Changes

- The dock has a Notes button (N) while recording: a card drops down under the pill with the
  recording's notes, saved as they are typed and when the dock hides or the recording stops.
  They are the same notes as in Details (and Studio's Briefing).
- Settings → General gains "Switch to the recording dock when a recording starts"
  (`dock_when_recording`, off by default). A quick note leaves the window as it is.
- Two editors of the same notes no longer undo each other: the window reloads the recording
  when it comes back from the dock, and Studio's Briefing saves its notes field only when it was
  typed in.

## Capabilities

### Modified Capabilities

- `desktop-app`

## Impact

`src/echo_app/ui/record_dock.py`, `main_window.py`, `window_capture.py`, `dialogs.py`, `theme.py`;
`src/echo_app/settings.py`; `src/echo_studio/home.py`; `tests/test_record_dock.py`,
`tests/test_studio_home.py`; `docs/guide.md`. No new dependency.

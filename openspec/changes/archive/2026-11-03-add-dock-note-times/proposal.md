## Why

A note typed in the dock during a call says what mattered, but not when. The user then has to
find the moment in the audio, and the minutes cannot tie the note to what was said then, as they
do for a marker.

## What Changes

- Ctrl+T in the dock's notes writes the recording's time where the cursor is (`[12:34] `, on a
  line of its own).
- Echo Studio sends a note line that starts with a time with the passage said around it, as it
  does for a marked moment (recorded in `refine-studio-record-and-actions`).

## Capabilities

### Modified Capabilities

- `desktop-app`

## Impact

`src/echo_app/ui/record_dock.py`, `dialogs.py` (the shortcut list); `tests/test_record_dock.py`;
`docs/guide.md`. No new dependency.

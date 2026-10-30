# Click the text to move playback

## Why

Moving playback to a place in the transcript took Ctrl+click, which few find, and it jumped to the
start of the passage, which can be half a minute before the word. Clicking where you are reading
should put the playhead there, or close to it.

## What Changes

- A plain click in the transcript that selects nothing moves playback near the clicked word,
  half a second early; playing keeps playing, paused stays paused.
- Ctrl+click is unchanged: plays from the start of the passage.

## Impact

`ui/editor.py` (the click), `ui/transcript.py` (`time_at`), `ui/main_window.py` (wiring),
`tests/test_ui.py`, `docs/guide.md`, `CHANGELOG.md`.

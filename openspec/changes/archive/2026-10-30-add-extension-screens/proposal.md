# Screens, passages and profile sections for extensions

## Why

Echo Studio's next features (open items across the library, questions over a recording or the
library) are not views of one recording. They need a place in the window, a way to send the
user to a passage, a place in a person's profile, and search results at the passage level. The
roadmap planned these as Echo base hooks shipped before the Studio features that use them.

## What Changes

- `MainWindow.add_screen(title, icon, widget, shortcut)`: a screen in place of the selected
  recording, opened by a checkable button beside People.
- `MainWindow.show_recording(id, at=None)`: select a recording and play it from `at`.
- Hook `person_sections(name) -> [(title, widget)]`, shown under a person's notes in People.
- `Index.passages(query, tags, limit, context)`: the passages matching a search, with recording,
  times, speaker and text.

## Capabilities

### Modified Capabilities

- `desktop-app`

## Impact

`ui/main_window.py`, `ui/recorder_panel.py` (`add_corner(before=)`), `ui/people.py`, `index.py`,
`extensions.py` (docstring), `tests/test_extensions.py`, `tests/test_speaker_search.py`,
`docs/design.md`, `CHANGELOG.md`.

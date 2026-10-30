# Action items

## Why

A summary's next steps are the part of a meeting people act on, and as prose they are hard to
track: nobody sees what is still open across meetings, or what one person owes.

## What Changes

- After each summary, a second short request turns its next steps into `actions.json` in the
  recording's folder: text, owner (a name as Echo knows it), due date, the time in the audio
  where it came up, and a done flag. Summarizing again keeps the checks of items whose text is
  the same.
- The Summary view lists them as checkboxes, each with a button that plays where it came up.
- A Pending screen (button beside People, Ctrl+Shift+T) gathers the open items of the whole
  library, filtered by person and tag.
- A person's profile in People shows their open items.

## Capabilities

### New Capabilities

- `studio-actions`

## Impact

`src/echo_studio/actions.py`, `actions_ui.py` (new); `summary.py` (`finish`), `jobs.py`, `cli.py`,
`ui.py`, `__init__.py`; `tests/test_studio.py`; `docs/guide.md`. Uses Echo's `add_screen`,
`show_recording` and `person_sections` (`add-extension-screens`).

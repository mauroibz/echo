# A bundle of recordings to paste into an assistant

## Why

Handing a meeting to a language model took several trips: copy the transcript, open Minutes and
copy the summary, retype the action items, and again for each recording. The parts are already
plain files; what was missing is one action that puts the chosen ones together.

## What Changes

- Bundle (Ctrl+Shift+B, the list's menu, the selection bar, Export in the header): tick the parts,
  then Copy to the clipboard or Save as zip. Markdown, one note per recording.
- `echo-app bundle ID... [--parts] [--timestamps] [--out]`.
- A `bundle_parts(rec)` hook; Echo Studio offers the summary and the action items through it.
- The selection bar's Delete becomes its icon, to make room for Bundle in a 310 px sidebar.

## Capabilities

### Modified Capabilities

- `desktop-app`, `command-line`, `extensions`

## Impact

`src/echo_app/bundle.py` (new), `export.py` (the note header, shared), `extensions.py`, `cli.py`,
`ui/dialogs.py`, `ui/window_library.py`, `ui/main_window.py`; `src/echo_studio/__init__.py`,
`actions.py`; `tests/test_bundle.py`; `docs/guide.md`, `docs/design.md`, `README.md`, `CHANGELOG.md`.
No new dependency: the zip is the standard library's.

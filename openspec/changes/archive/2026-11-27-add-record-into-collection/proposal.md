# Record into a collection

## Why

Collections filed batches that were imported; a recording always went to the day-to-day list and
had to be moved by hand afterwards. Someone whose meetings mostly belong to one client wants that
client's collection as the place recordings go, and to choose the place before a meeting starts.

## What Changes

- A line under Record names where new recordings are filed and opens a menu to change it. The
  choice is a setting (`record_collection`) and stays.
- `recorder.start` takes the collection, so the recording is filed from its first moment.
- `echo-app record --collection NAME`.
- Echo Studio tells an imported batch from the day's work by `collections.apart`, so recorded
  meetings stay in the Briefing, the Action items page and calendar matching wherever they are filed.

## Capabilities

### Modified Capabilities

- `desktop-app`, `command-line`

## Impact

`src/echo_app/collections.py`, `recorder.py`, `settings.py`, `cli_rec.py`, `ui/recorder_panel.py`,
`ui/window_collections.py`; `src/echo_studio/home.py`, `actions.py`, `calendar.py`;
`tests/test_collections.py`; `docs/guide.md`, `docs/design.md`, `CHANGELOG.md`.

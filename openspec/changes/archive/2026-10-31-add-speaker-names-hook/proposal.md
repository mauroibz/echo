# Names an extension offers for speakers

## Why

Echo Studio knows who was invited to the meeting a recording belongs to. Those names should come
first when the naming bar asks who a speaker is.

## What Changes

- A `speaker_names(rec)` hook: the names an extension offers, listed first in the naming bar's
  completion, before the dictionary's people.

## Capabilities

### Modified Capabilities

- `extensions`

## Impact

`src/echo_app/extensions.py`, `ui/transcript_speakers.py`; `tests/test_extensions.py`; `CHANGELOG.md`.

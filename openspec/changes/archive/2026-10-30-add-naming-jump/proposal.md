# The naming bar's play goes to the passage

## Why

The bar that asks for a speaker's name plays a few seconds of them, but the playhead and the
text stayed where they were, so the user could not see what was being said or keep listening
from there.

## What Changes

- ▶ in the naming bar moves the playhead and the transcript to the passage it plays, even while
  the cursor is in the text.

## Capabilities

### Modified Capabilities

- `transcript-editor`

## Impact

`ui/transcript_speakers.py`, `ui/transcript.py` (`follow(jump=)`), `ui/player.py`
(`seek_shown`), `tests/test_ui_speaker_naming.py`, `docs/guide.md`, `CHANGELOG.md`.

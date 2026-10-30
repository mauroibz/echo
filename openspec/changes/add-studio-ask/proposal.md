# Ask a recording

## Why

Rereading an hour of transcript to find what someone said about one thing is slow. A question
answered from the transcript, citing the moments, gets there in seconds.

## What Changes

- An Ask view beside Transcript and Summary: questions about the shown recording, answered from
  its transcript with times and speakers. Each answer cites times as [m:ss]; a citation plays the
  recording from there. The conversation lasts while the recording is shown.
- `echo-app ask ID "question"`.

## Capabilities

### New Capabilities

- `studio-ask`

## Impact

`src/echo_studio/ask.py`, `ask_ui.py` (new); `__init__.py`, `cli.py`; `tests/test_studio.py`;
`docs/guide.md`. Uses Echo's `show_recording`.

# Summaries guided by the user's notes

## Why

A recording's notes and its markers are what the user thought mattered while it happened. A
summary that ignores them can bury the one thing the user wanted to keep.

## What Changes

- The notes and every marker (its time, its note, and the passage around it) go into the request
  ahead of the transcript, with an instruction to build the summary around them.
- What a summary is made from now covers the notes and markers too: editing a note marks the
  summary out of date. A recording with neither is hashed as before, so existing summaries stay
  current.

## Capabilities

### Modified Capabilities

- `studio-summaries`

## Impact

`src/echo_studio/summary.py` (`guide`, `source_sha`), `src/echo_studio/jobs.py`,
`tests/test_studio.py`, `docs/guide.md`.

# Proposal

## Why

Nobody reads two hours of transcript. The engine already notices suspicious passages (output
implausibly short for the duration, a retry that changed the text) and throws that knowledge
away. Showing it lets the user check the few passages that need checking.

## What Changes

- The worker records per-passage flags in `transcript.json`: `short` (fell below the words-per-
  second floor even after retries), `retried` (a fallback produced the kept text), and the
  model's average token log-probability when generation can return it cheaply.
- The editor shades flagged passages and shows the reason on hover; a count in the status bar
  ("4 passages to check"); next-flagged navigation (see add-edit-with-audio).
- Flags are advisory and disappear for a passage once the user edits it.

## Capabilities

### Modified Capabilities
- `transcription`: per-passage confidence flags in the output.
- `transcript-editor`: flagged passages shown.

## Impact

`worker/asr.py` (return flags with texts), `worker/service.py` (store them),
`ui/transcript.py`, transcript JSON version 2 with backward-compatible reading.

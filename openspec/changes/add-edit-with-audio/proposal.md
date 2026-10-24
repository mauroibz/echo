# Proposal

## Why

Correcting a transcript means hearing the passage again. Today that is Ctrl+click, then back
to the keyboard. A keyboard loop turns correction from a chore into something people do, and
it is what feeds the dictionary.

## What Changes

- `Ctrl+.` plays the passage under the cursor; pressing again stops. `Ctrl+,`/`Ctrl+;` move to
  the previous or next passage and play it. Playback pauses automatically while the user types
  and resumes from the passage start when typing stops for a second (configurable off).
- Typing speed control applies (the existing speed setting).
- A "review" ordering: `Ctrl+Shift+.` jumps to the next passage flagged low confidence
  (see add-low-confidence-marking), so a long transcript can be checked where it matters.

## Capabilities

### Modified Capabilities
- `transcript-editor`: play the passage under the cursor; auto-pause while typing.

## Impact

`ui/transcript.py`, `ui/player.py` (play a span), shortcuts dialog, README.

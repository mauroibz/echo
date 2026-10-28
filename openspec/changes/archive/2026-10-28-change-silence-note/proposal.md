# Proposal

## Why

The user records with a software noise gate on the microphone. A gate sends exact digital
silence whenever nobody speaks, so the hint "No sound from this input for N seconds…" kept
appearing and disappearing under the recorder controls, two lines of text pushing the sidebar up
and down while recording.

## What Changes

- In the sidebar the hint becomes a few words drawn on the empty level meter ("No sound for
  12 s"), with the advice in its tooltip. Nothing moves.
- The welcome screen, where the user checks the microphone for the first time, keeps the full
  hint under its meter.

## Capabilities

### Modified Capabilities
- `audio-capture`: where the silent-input hint is shown.

# Proposal

## Why

Transcription is the reason Echo exists. Recordings are long and spoken freely, so the
transcriber must handle hours of audio, skip silence and noise, keep timing for each passage,
survive interruptions, and never get in the way of recording or editing.

## What Changes

- A background transcription worker that processes queued recordings one at a time on the GPU
  (CPU fallback), started on demand and exiting when idle to free GPU memory.
- Speech detection splits audio into passages of at most about 30 seconds at natural pauses;
  each passage keeps its start and end time; long pauses become paragraph breaks.
- Cohere Transcribe with the Surus Spanish adapter (on by default, configurable), pinned
  revisions, loaded without remote code and without librosa.
- Progress with time remaining, cancellation, resumption after a crash or restart, and clear
  errors.
- The model transcript is stored separately from the user's edits; re-transcribing never
  overwrites edits.
- CLI: `echo-app transcribe`, `echo-app models download`, and model status in doctor.

## Capabilities

### New Capabilities
- `transcription`: turning a recording's speech into timed Spanish text in the background.

### Modified Capabilities

## Impact

New package `src/echo_app/worker/` (imports torch, transformers, peft, silero-vad; never
imported by the UI). Requires the full install profile and the downloaded models.

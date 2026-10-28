# Proposal

## Why

In a real three-person meeting the user fixed a passage with "Said by" and expected Echo to
learn from it: the passages that sound like it should follow. A fix only changed that passage.
The same meeting showed a second problem: the person suggested for a speaker was wrong because
their stored voice had been learned five times from this one recording (each new transcription
and each renaming folded the speaker's voice in again), and the first wrong naming had become
the voice.

## What Changes

- The worker keeps each passage's voiceprint (the embedding speakers are clustered from) in
  `transcript.voices.json`.
- After a "Said by" fix, or undoing one, the window reassigns the other passages: each speaker is
  described by its passages as the user has them, and a passage moves to another speaker only if
  it sounds clearly closer to them. The result is a file of its own, read over the model's
  transcript, and "Back to the speakers Echo found" on a speaker's label removes it.
- A person's voice is the mean of one part per recording. Naming them again in a recording
  replaces that recording's part; renaming a speaker or merging it into someone else takes the
  old name's part back.

Out of scope: reassigning from words split off a passage (they have no voiceprint of their own),
transcripts made before voiceprints were kept (they need one new transcription).

## Capabilities

### Modified Capabilities
- `transcript-editor`: fixes reassign the passages that sound the same; voices are learned once
  per recording.

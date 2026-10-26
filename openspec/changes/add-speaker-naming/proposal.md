# Proposal

## Why

Speakers are labeled "Speaker 1", "Speaker 2", and naming one means noticing that the label in
the margin can be clicked. Most recordings stay unnamed, so exports read "Speaker 2: …" and
Echo never learns the voices it could recognize next time. The user is in nearly every
recording and is asked about like a stranger each time.

## What Changes

- **A naming bar over the transcript.** After a recording with speakers is transcribed, a slim
  bar at the top asks about one unnamed speaker at a time, the one with the most speech first:
  "Speaker 2 sounds like Ana. [Yes, Ana] [Someone else…] [Not now]" when the voice matches a
  person named before, or "Who is speaker 2? [name ⏎] [It's me] [Not now]" otherwise. A ▶
  plays a few seconds of that speaker. Answering moves to the next speaker; "Not now" hides the
  bar for that recording. It never takes focus or blocks editing and playback, and it waits
  while the dictionary's suggestion chip is showing.
- **Echo knows your voice.** "It's me" names the speaker with your name (asked once, then kept
  in settings as "Your name") and remembers your voice. From then on Echo names you itself in
  every recording where your voice is recognized, and in a recorded call the speaker on the
  microphone track is you without any voice match. You are never asked about yourself again.
- **Other people stay confirmed.** A voice that matches someone you named before is offered
  ("sounds like Ana"), one click to accept; confirming it refines their voice.
- "Your name" can be changed in Settings. The margin labels and their menu stay as they are.

Out of scope: naming before recording or on import (names cannot be matched to voices until
the speakers are found), naming in a linked set's combined view (done on its parts, as now).

## Capabilities

### Modified Capabilities
- `transcript-editor`: the naming bar.
- `transcription`: the user's own voice is named automatically.

## Impact

`settings.py` (`your_name`), `worker/service.py` (track per speaker, naming the user),
`ui/transcript.py` (the bar), `ui/dialogs.py` (Your name), `README.md`, `docs/design.md`,
`CHANGELOG.md`. No new dependencies; voices stay in `voices.json`, on this computer only.

# Proposal

## Why

The user's calls have them alone on the microphone and several people on the other side. Cutting
out interruptions with the segmentation model on the mixed sound (add-speaker-turns) cut real
calls into many short pieces: on a 20-minute call, 184 passages instead of 60, 52 of them under
1.5 s, 11 heard as "Gracias.", and a repetition loop in one. It also put a piece said over
someone on the louder track, so it could not get the interrupter's name.

Looking into it showed that two of the user's four calls had the same sound on both tracks:
WirePlumber had moved the computer-audio capture to the noise gate's source the user had chosen
for Echo's microphone, because both of Echo's captures had one application name.

## What Changes

- In a call, a change of side is cut where the other track speaks, without a model; segmentation
  runs on the computer audio alone, for changes between the people on the call. Only turns of a
  second or more are cut in a call.
- A piece cut out of someone else's speech in a call goes to the track that speaks in it.
- A call whose tracks are one sound recorded twice is labeled like a single microphone.
- The computer-audio capture has an application name of its own, so WirePlumber does not move it
  where the user moved the microphone.

## Capabilities

### Modified Capabilities
- `transcription`: speaker changes in calls.
- `audio-capture`: the computer-audio capture is not moved with the microphone.

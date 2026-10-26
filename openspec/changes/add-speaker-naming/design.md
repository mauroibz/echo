# Design

## Context

The worker labels passages with speaker numbers and stores, per recording, each speaker's voice
centroid and the names it suggests from `voices.json` (similarity at least 0.85). Names the user
gives live in `meta.json` (`speakers`: number to name) and are what exports, `info` and the
margin show. Naming happens through a menu on the margin label; a suggested name shows as
"Ana?". Naming adds the person to the dictionary and folds the centroid into their voice. Call
recordings know which track each passage is on.

## Decisions

### One bar, one speaker at a time

The bar reuses the dictionary chip's look (a `QFrame` named `chip` above the transcript) and its
manners: it appears after the work that produced it, asks one thing, and is dismissed with a
click. Speakers are asked about in order of how much they speak, since naming the main voices
first makes the transcript readable soonest. A prompt per speaker is also what lets a ▶ play
just that voice: naming a voice without hearing it is guessing. The sample is the speaker's
longest passage, cut to 6 s, played through the panel's existing `play_span`.

The dictionary chip goes first when both have something to offer: it answers a save the user
just made. The bar comes back when the chip is gone.

### Not now is per recording and permanent

"Not now" sets `naming_dismissed` in `meta.json`. A recording the user did not want to name is
not worth asking about again; the margin still names speakers one by one.

### The user's name in settings, their voice in voices.json

"Your name" is a setting (`your_name`), not a dictionary flag: it is one value about the person
using Echo, and the dictionary is a list of names for transcription. The voice is an ordinary
entry in `voices.json` under that name, so recognition needs nothing new. Changing the name in
Settings renames the voice entry.

### The worker names the user, the user names everyone else

After labeling, the worker writes the user's name into `meta.json` for at most one speaker: in a
call, the only speaker on the microphone track (the track says who it is, no voice needed);
otherwise the speaker whose voice the worker already suggests as the user's. A speaker the user
already named is left alone. Other people are only suggested, as now, because a wrong name
written silently into a transcript is worse than one more click, and the 0.85 threshold was
measured on audiobook readers, not on calls.

The call rule also teaches Echo the user's voice: its centroid is folded into the user's voice,
since the track makes it certain. A voice match is not folded back in, so one wrong match cannot
drift the voice.

### What the worker records for the bar

The transcript's `speakers` record gains `tracks` (speaker number to 0 for the microphone, 1 for
the computer audio, by where most of the speaker's passages are) for calls, and `me` (the number
the worker named as the user). The bar does not ask about `me`, and offers "It's me" only while
nobody in the recording is the user.

## Decisions made while implementing

- **At the top of the transcript,** under its header, as the user asked; the dictionary chip
  stays at the bottom, where it follows the typing that produced it.
- **The bar is refreshed on every refresh of the panel,** not only when the transcript is
  reloaded, so names given in the margin, from another window or by the worker are reflected
  without reselecting the recording.
- **A suggestion that is the user, or someone already named in this recording,** is not offered;
  the bar asks for a name instead.
- **"Someone else…" and the name field** use the dictionary's people as completions, as the
  margin's naming dialog does.


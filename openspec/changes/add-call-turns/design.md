# Design

## Measurements

**Synthetic calls.** Twelve calls of about 6.5 minutes built from the Multilingual LibriSpeech
Spanish readers of add-speaker-turns (six from the tuning readers, six from the held-out ones):
speaker 0 on the microphone track through a noise gate (exact zeros where they are quiet, 100 ms
hold), two or three people on the computer track (band-limited, with a noise floor), turns and
interruptions as in add-speaker-turns, in a pause or over someone. Held-out half, labeled with
the product code; "right" means labeled as the interrupter:

| Cuts | Speech labeled right | Interruptions across sides right | Between people on the call right | False changes |
|---|---|---|---|---|
| None | 86.9% | 0 of 103 | 0 of 55 | 0 |
| Segmentation on the mix, 0.4 s (add-speaker-turns) | 95.1% | 54 | 41 | 0 |
| By track + segmentation of the computer audio, 0.4 s | 96.8% | 88 | 41 | 0 |
| Same, 0.7 s | 96.6% | 75 | 39 | 0 |
| Same, 1 s | 95.7% | 58 | 33 | 0 |

On the tuning half, a track "speaks" rule that required it to be twice as loud as the other
showed 27 of 56 interruptions said over someone as someone else; without it, 55 of 56. Placing a
cut piece on the track that speaks in it, instead of the louder one, took those shown from the
mix cuts from 32 of 56 to 46.

**A real call** (20 minutes, the user and three to four people, tracks clean), transcribed on a
copy with each method:

| Cuts | Passages | Under 1.5 s | "Gracias." | Flagged | Words |
|---|---|---|---|---|---|
| None | 60 | 0 | 0 | 3 | 3348 |
| Segmentation on the mix, 0.4 s | 184 | 52 | 11 | 33 | 3215 |
| By track + computer audio, 0.4 s | 276 | 115 | 25 | 58 | 3163 |
| By track only, 0.4 s | 259 | 103 | 21 | 49 | 3144 |
| By track + computer audio, 0.7 s | 157 | 29 | 4 | 25 | 3172 |
| By track + computer audio, 1 s | 122 | 6 | 1 | 18 | 3213 |

The synthetic calls have no backchannels, breaths or line noise; the real one does, and at 0.4 s
every "mm" became a piece. Under 1.5 s, pieces mixed real interjections (a "yes" or an
"okay") with the last words of the other person's sentence.
From 1 s the transcript is close to the uncut one and cross-side interruptions of a second or
more are still cut. Shorter interruptions in calls are not found; in recordings from one
microphone, 0.4 s stays.

**Copied tracks.** In two real calls under 1% of speech frames had the two tracks within 12%
(about 1 dB) of each other; in two later ones, 100% and 54%, with the tracks correlated at 0.9 to
1.0. WirePlumber's state held a target for `Input/Audio:application.name:Echo`, a noise gate's
virtual source Echo's microphone had once been moved to, and WirePlumber had moved every input
stream named "Echo" there, the computer-audio capture included.

## Decisions

### Sides from the tracks, people on the call from the model

With headphones each track hears one side, so where the other track has sound (above an RMS of
100 in 50 ms frames; a gate's silence and a quiet line are below) is a change of side, at no
cost and without a model. Segmentation runs on the computer audio alone, where everyone but the
user is, for changes among them. The spans of both are cut at each other's edges
(`split_spans`), so a change between two people inside the call's turn keeps its piece.

### One second in calls

Taken from the real call above: the shorter minimum catches more on synthetic calls but makes a
real transcript worse than having no cuts.

### Copied tracks are one microphone

A call whose tracks are at the same level in 30% or more of the speech frames is labeled as from
one microphone (segmentation on the mix, no tracks in the speakers record), since the tracks say
nothing about sides there. The existing recordings stay as they are on disk.

### The computer audio has its own name

`application.name="Echo computer audio"` and `node.name="echo-recorder-computer"`. WirePlumber keys
its remembered targets by application name, so a move of the microphone no longer applies to it,
and it still follows the default output since it has no target. The microphone keeps "Echo", so
the user's gate keeps applying to it.

## Decisions made while implementing

- The tracks are decoded once per job at 4 kHz, as before, and the computer audio once more at
  16 kHz for segmentation; the mix the model transcribes is unchanged.

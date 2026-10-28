# Design

## Measurements

The synthetic conversations of add-speaker-turns (16: tuning and held-out readers, two and three
speakers, clean and room), labeled by the product code, then a simulated user who fixes the
longest wrongly labeled passages first, giving each to the number the person already has, or to
a new one if they have none. "Labeled right" is the share of speech time whose passage carries
its speaker; "made wrong" counts passages that were right after the fixes and wrong after the
reassignment, over all 16.

| Clustering | Fixes | As found | Fixes only | Fixes + reassigned | Made wrong |
|---|---|---|---|---|---|
| 0.35 (today's) | 3 | 94.5% | 97.7% | 98.6% | 11 |
| 0.35 | 5 | 94.5% | 98.5% | 99.1% | 10 |
| 0.35 | 10 | 94.5% | 99.6% | 99.6% | 10 |
| 0.5 (people merged) | 3 | 75.6% | 82.1% | 83.5% | 10 |
| 0.5 | 10 | 75.6% | 89.4% | 89.5% | 9 |

The 0.5 rows stand for a recording where people were merged: nine people had no number of their
own. With 5 fixes, the share of such a person's speech labeled as them went from 34% (the fixed
passages alone) to 40%; at 0.35, the one merged person went from 69% to 100%. Where the
embeddings can barely tell two voices apart, as for those nine, reassignment cannot either.

Describing each speaker by its fixed passages alone, which was tried first, made things worse
(97.7% → 95.0% with 3 fixes, 42 passages made wrong, then 86.8% with 10): the passages a user
fixes are the ones whose voice sounded closest to someone else.

## Decisions

### Reassign in the window, from stored voiceprints

Reassigning needs each passage's embedding. Computing them again means decoding the audio and
running the embedding model, which only the worker can do (onnxruntime), for a job the user
expects at once after a click. The worker already computes them; it now keeps them, rounded to
four decimals (about 1 MB for an hour). With them, reassigning is a few hundred dot products of
256 numbers, in pure Python in the window.

### K-means from the fixed labels, with a margin

Each speaker is the mean of its passages as the user has them (fixes applied), each passage goes
to the nearest speaker, twice. A passage moves only if it is 0.1 closer (cosine) to the other
speaker than to its own: on the measurement above that halved the good passages made wrong
(20 → 11 with 3 fixes) for the same gain. Fixed passages never move.

### A file over the transcript, not a change to it

`transcript.json` is the model's output and is not changed after a run. The reassignment is
`transcript.relabeled.json` (speakers per passage, centroids, count, and the transcript it
belongs to); `Recording.transcript()` reads it over the model's, so labels, exports, search,
people and sets follow without change. Undo deletes it; a new transcription removes it.

### One part per recording in a voice

`voices.json` keeps, per person, the mean (read by recognition as before), the number of
recordings, and the part each recording gave. A voice learned before parts were kept counts as
the mean times its count; new parts are added to it. Naming replaces the recording's part, and a
rename or merge that leaves a name out of the recording takes its part back. When all parts are
gone the voice is forgotten.

## Decisions made while implementing

- The reassignment runs on its own after every whole-passage fix and every undo of a fix; there
  is no separate command. Named speakers' voice parts are refreshed from the new centroids.
- The relabeled speakers are stored after merges (a merged speaker's number), so "Separate again"
  after a reassignment separates nothing that moved; undoing the reassignment brings it back.

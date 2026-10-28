# Design

## Measurements

No annotated recordings of real meetings were available and the user had no time to annotate,
so the test material is built with its ground truth. Spanish speakers from the Multilingual
LibriSpeech test set (20 readers, 60 utterances each) are joined into conversations of about
6.5 minutes: turns of two to five utterances by one speaker, and inside them, every 4 to 14 s,
an interruption of 0.5 to 2.5 s (two to seven words) cut at quiet points from another speaker,
either in a short pause of the main speaker ("gap") or on top of them ("overlap"). Turn changes
mostly have pauses under 2 s, so the planner joins them into passages as in a quick
conversation. Half the conversations have two speakers, half three; half are clean, half go
through one room channel (reverb with a 0.4 s decay, a mild low-pass and noise at 15 to 25 dB
SNR). Ten readers were used to tune, the other ten only to test. Speech detection is Echo's
(silero-vad with Echo's settings) and passages are Echo's planner's.

Scoring is per 10 ms frame where exactly one person speaks, after mapping labels to people. An
interruption is "shown" when at least 40% of its speech carries a label other than the main
speaker's, and "right" when it carries the interrupter's. A false change is a label run shorter
than 3 s that is wrong for most of its length with no interruption or turn change within 1 s.

Held-out set, 8 conversations, 52 minutes, 216 interruptions:

| Labeling | Speech labeled right | Interruptions shown | Interruptions right | False changes / 10 min | Speaker count right |
|---|---|---|---|---|---|
| Today (per passage, 0.4) | 88.4% | 5.1% | 2.8% | 0 | 7/8 |
| Cuts from segmentation, 0.35 | 92.3% | 68.1% | 64.8% | 2.1 | 7/8 |

On the tuning set the same comparison was 84.3% → 93.8% labeled right, 15.7% → 72.8% shown,
and the speaker count right in 5 → 7 of 8 conversations. By kind on the held-out set, the cuts
show 7 of 25 gap interruptions under 1 s, 59 of 82 longer gap ones, and 81 of 109 overlapping
ones: under a second, the segmentation model often misses them.

Embedding models, today's labeling on the tuning set, by threshold (0.3 / 0.4 / 0.5), speaker
count right of 8: ResNet34 (today's) 6 / 5 / 5; ResNet34-LM 7 / 6 / 5; ResNet293-LM 6 / 6 / 5
at a sixth of the speed; CAM++-LM 6 / 6 / 5. No larger model was better, so the embedding model
stays and the threshold moves: with the cuts, 0.35 and 0.30 gave the same counts (7 of 8), and
0.35 is the smaller step from what the earlier LibriVox measurement found safe (0.30 to 0.55).

Recognition on the cut pieces (real model, GPU, three held-out conversations): 45% of gap
interruptions ended up as their own passage with at least half of their words, labeled as the
interrupter. The rest were either not found by segmentation or cut a little early or late. The
interruptions in this material are fragments cut from read sentences, which the model
transcribes badly even alone (it often answers "Gracias." for a half-second fragment), so this
number understates what complete short utterances will do; it is a floor, not a measurement of
real meetings, and task 1.6 is that measurement.

Speed: segmentation plus embeddings ran at about 78× real time on a 6-core processor (today's
embeddings alone: 120×), so an hour of audio adds about 45 s on the processor.

## Decisions

### Cut before recognition, not label after

The model times passages, not words, so a label for part of a passage needs to know which words
are that part. Cutting the passage at the change before recognition makes the interruption a
passage like any other: its own text, speaker and paragraph, and the editor, exports, search,
margin, merges and "Said by" fixes work without change. The cost is that a cut can fall inside
an overlapped word; cuts are moved to the quietest point within 0.25 s, which for a gap
interruption is the pause around it.

### Segmentation model

pyannote's segmentation-3.0 (MIT), as exported to ONNX by onnx-community (6 MB), pinned. It
looks at 10 s of audio and says, every 17 ms, which of up to three local speakers is talking,
including two at once. It runs over each passage in 10 s windows every 2.5 s; local speakers are
matched between windows on their overlap, and a frame counts as a speaker's when at least 40% of
the windows that cover it say so. The passage's main voice is the local speaker with the most
frames; anyone else for 0.4 s or more is a cut (spans less than 1 s apart are one). The
original repository is gated; this export is not, so the download needs no token, like the
embedding model. No new dependency: `onnxruntime` already runs the embedding model.

### Who an interruption is

A cut piece of 1.5 s or more gets an embedding and is clustered with the rest. The segmentation
model says it is not the main voice, so if it clusters with the voice around it anyway, or is
too short to embed, it is labeled as the speaker other than that voice whose centroid is nearest
to its embedding (0.4 s or more of audio), or, with only one other speaker, as that one. Taking
the neighbor's speaker, as before, would undo the cut. Forcing the longer ones too raised the
interruptions labeled right on the tuning set (at 0.30) from 59.2% to 61.8%, with false changes
from 1.2 to 1.6 per 10 minutes.

### Resume

The cuts are found once, after speech detection, and kept in the partial file next to the
regions; passages are planned from both, so a resumed job transcribes the same passages.

## Decisions made while implementing

- The numbers above are from the product code (`speakers.local_activity`,
  `speakers.interruptions`, `planning.cut`, `speakers.label`) run on the same material, not from
  the prototype it was tuned with; they agree within a point.
- The window hop is 148 frames (2.4975 s) rather than exactly 2.5 s, and the last window starts
  on a frame, so every window's frames line up with the passage's.
- "The voice around" an interruption is the nearest passage before it that is not itself an
  interruption (after it, at the start of a recording). In a call, the other speaker must be on
  the interruption's own track; with nobody else there it keeps the label it had.
- `models.speaker_cached()` now means both speaker models, so the download dialog and doctor
  offer the 6 MB to someone who already has the embedding model; the size shown is what is
  missing (`models.speaker_download_mb`). Embedding alone still works without segmentation.
- A partial file written before this change has results numbered by uncut passages, so a job
  resumed from it is finished without cuts rather than recomputed.
- The progress stage while segmenting is "speakers" ("Telling speakers apart…"), the stage the
  window already shows for the embedding pass.
- On the first real meeting transcribed with the cuts (an hour, three people), 21 of the 96
  passages under 1.5 s came back as "Gracias.", with log-probabilities as high as real words
  (-0.05 to -0.65), against none in the transcripts made before the cuts, which had almost no
  passages that short. Padding the pieces with 0.5 s of silence brought it to 8 and 1 s to 1, but
  the model then invented other text instead ("El rey de la República de Chile", "¿Qué es lo
  que se llama?"); widening them with 0.3 s of the real audio around made it 24. So a passage
  under 1.5 s whose whole text is "Gracias." is shown without text, the model's words kept in
  the segment as `dropped`. These pieces had also been labeled as a speaker of their own.

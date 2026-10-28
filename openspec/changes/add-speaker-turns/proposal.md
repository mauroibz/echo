# Proposal

## Why

Speaker labels are per passage, and a passage joins speech across pauses under 2 s. A short
interruption by someone else ("¿y cuánto sale?", "claro, claro") inside a long paragraph is
therefore labeled as the person speaking around it, and so is a quick change of turn. The user
sees this in real meetings. A passage that holds two voices also blurs its embedding, which is
how two people get merged into one speaker.

## What Changes

- Before recognition, a small speaker segmentation model (6 MB, ONNX, run with `onnxruntime` on
  the processor, as the embedding model is) finds where someone other than a passage's main
  voice speaks for 0.4 s or more. The passage is cut there, so the interruption becomes its own
  passage with its own text, speaker and paragraph.
- An interruption too short for an embedding of its own is labeled as the nearest speaker other
  than the one around it, instead of taking its neighbor's speaker.
- The clustering threshold goes from 0.4 to 0.35: on Spanish speakers 0.4 merged two people
  into one in three of eight recordings.
- The segmentation model is pinned and downloaded with the speaker model; without it, labeling
  works as before.

Out of scope: overlapping speech as two labels at once (the text has one speaker per piece),
word-level timing, a new embedding model (larger ones measured no better here).

## Capabilities

### Modified Capabilities
- `transcription`: speaker changes inside a passage.

## Impact

`models.py` (a pinned segmentation model, optional like the speaker model), `worker/speakers.py`
(segmentation, cuts, labeling of interruptions), `worker/planning.py` (passages cut at speaker
changes), `worker/service.py` (the cut before recognition, kept in the partial file for resume),
`doctor.py`, `ui/dialogs.py` (download size), `README.md`, `docs/design.md`, `CHANGELOG.md`.
No new Python dependency.

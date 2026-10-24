# Proposal

## Why

Interviews and meetings read badly without knowing who said what. The model does not separate
speakers; passage boundaries from speech detection are already there to label.

## What Changes

- Speaker embeddings per passage from a small ONNX speaker model run with `onnxruntime` on the
  CPU, clustered per recording; passages get `speaker: 1..N` in the transcript.
- The editor shows a label per paragraph start; the user names a speaker once and the name
  applies to the whole recording. Names of people in the dictionary are offered first, and a
  named speaker's embedding is kept with the dictionary entry so the same person is recognized
  in later recordings.
- Off for recordings with one detected speaker; a per-recording toggle for monologues.

## Capabilities

### Modified Capabilities
- `transcription`: speaker per passage.
- `dictionary`: a person may carry a voice signature.
- `transcript-editor`: speaker labels and naming.

## Impact

New `worker/speakers.py`, a pinned ONNX model in `models.py` (small, downloaded with the
others), `onnxruntime` in the transcription profiles, `dictionary.py` (embeddings per
person), editor labels, export (speaker prefixes in TXT and Markdown, voice tags in VTT).

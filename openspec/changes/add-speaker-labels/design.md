# Design

## Decisions

- **Model.** A WeSpeaker or 3D-Speaker ResNet speaker-embedding model exported to ONNX (a few
  tens of MB), pinned by revision like the ASR models, running on CPU through `onnxruntime` so
  it works on every profile including `cpu`. `pyannote` is not chosen: gated model, heavier
  dependency tree, and GPU-oriented.
- **Clustering.** Agglomerative clustering on cosine distance with a fixed threshold tuned on
  the author's interviews; passages shorter than 1.5 s inherit the neighboring speaker.
- **Naming.** Labels live in `transcript.json` as cluster ids; names in `meta.json`
  (`speakers: {"1": "Lucía"}`). Naming a speaker with a dictionary person stores the cluster
  centroid on that entry; on later recordings a cluster within the threshold of a stored
  centroid is pre-named, shown as a suggestion the user confirms with one click.
- **Where it runs.** In the worker after recognition, as a separate stage with its own progress,
  so an interrupted job resumes without redoing recognition.

## Decisions made while implementing

- **Model**: `Wespeaker/wespeaker-voxceleb-resnet34` at revision ff1ac5bc (Apache-2.0, not
  gated, 26.5 MB ONNX, 256-dimensional embeddings from 80-bin filterbanks). It is optional:
  `models.OPTIONAL`, downloaded by `echo-app models download` and by the model dialog, which
  offers just this file to installs that already have the transcription model. Without it,
  transcripts simply have no speakers.
- **Features** are Kaldi's fbank computed in numpy (torchaudio is not in the environment):
  25 ms Hamming frames every 10 ms, DC removal, pre-emphasis 0.97, 512-point FFT power, 80 mel
  bins from 20 Hz, log, mean removed. Checked against torchaudio's `kaldi.fbank` in a throwaway
  environment: largest difference 1.2e-3 on values from -13 to 11.
- **Clustering** merges cluster centroids (cosine) and updates only the merged row, so it stays
  fast for hours of passages. Threshold 0.4: safe range measured 0.15 to 0.55 (see design.md).
- **Tuning data**: conversations of alternating whole passages from different LibriVox readers
  (Miau and Robinson Crusoe are read by several people), plus the same conversations through one
  shared phone-band, Opus 12 kb/s and noise channel; single-reader recordings for monologues.
- **Speaker changes start paragraphs** in the transcript, so a label always sits at a
  paragraph's start.
- **Voices** live in `voices.json` next to `glossary.toml` (256 numbers per person would bury
  the names); removing or merging people in the dictionary carries their voice along. Naming a
  speaker with a new name adds that person to the dictionary.
- **Suggestions** are stored in the transcript (`speakers.suggested`) and shown as "Ana?"; a
  click confirms or renames. Names given are in `meta.json` (`speakers`).
- **Exports**: "Name:" paragraphs in text and Markdown (bold), "Name:" on the first SRT cue of a
  turn, `<v Name>` in VTT, a `speaker` field in JSON.
- **End to end** with the real worker: two 4-minute conversations; both found 2 speakers; the
  first labeled 100% of speech consistently with the true reader, the second 88.8% (the rest
  were passages straddling a turn); naming the first conversation's reader "Marta" made the
  second conversation, from a different chapter of the same reader, suggest "Marta" for the
  right speaker.

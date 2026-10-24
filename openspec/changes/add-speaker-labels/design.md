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

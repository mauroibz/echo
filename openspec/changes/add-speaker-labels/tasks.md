# Tasks

- [ ] 1.1 Pick and pin the embedding model; `worker/speakers.py` embeddings and clustering; tune the threshold on three real interviews and record the numbers (needs hardware: GPU and the downloaded model)
- [x] 1.2 Worker stage with progress and resume; `speaker` per segment; transcript version bump
- [x] 1.3 Editor labels at paragraph starts, naming, dictionary suggestions and stored centroids
- [x] 1.4 Exports with speaker names; README

## Blocked

- **1.1** is implemented and tuned, but not on real interviews: none were available. The
  threshold (0.4) and the recognition threshold (0.85) come from conversations built from nine
  LibriVox readers, with and without a shared degraded channel, plus the user's own monologue
  (numbers in design.md and docs/design.md). A person should transcribe three real interviews
  recorded on one microphone (two or three people, quick turns), check in the editor that the
  speaker labels follow the voices, and if they drift, rerun the tuning script approach with
  those recordings and adjust `speakers.THRESHOLD`.

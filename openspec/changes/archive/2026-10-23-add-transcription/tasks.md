# Tasks

## 1. Planning and audio

- [x] 1.1 Implement passage planning from speech regions (28 s cap, widest-pause cuts, long-region splitting, paragraph flags); verify with unit tests on synthetic region lists
- [x] 1.2 Implement crop-aware decoding to 16 kHz int16 and time offsetting; verify with a test on a generated file with a crop

## 2. Model and worker

- [x] 2.1 Implement model loading (pinned snapshots, librosa-free feature extractor, bf16 on CUDA, float32 CPU fallback, adapter toggle) and batched recognition with OOM backoff; verify by transcribing a synthetic Spanish clip
- [x] 2.2 Implement the worker loop: lock, queue ordering, progress file, partial results and resume, cancellation, error reporting, idle exit; verify with tests using a stub recognizer
- [x] 2.3 Add `ensure_worker()` client and `echo-app transcribe [ID...|--all] [--wait] [--no-adapter]`, `echo-app models download`; verify by transcribing a 20-minute Spanish audiobook chapter end to end and reporting speed
- [x] 2.4 Verify resume against the real model: kill the worker mid-way through the chapter, restart, confirm only remaining passages are processed

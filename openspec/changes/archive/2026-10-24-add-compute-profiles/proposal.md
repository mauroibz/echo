# Proposal

## Why

"With transcription" today means "with an NVIDIA GPU": the `worker` extra resolves a torch
wheel with CUDA bundled (3.5 GB) and the engine's CPU path, though present, is never installed
on purpose, never measured and never explained to the user. Many laptops and every AMD machine
are left out. Decision taken for this change: quality over throughput. Echo keeps one model
(Cohere Transcribe with the Surus adapter) and makes it run as well as it can on CPU and on
AMD GPUs; alternative, smaller models are out of scope.

## What Changes

- Three mutually exclusive install profiles for transcription: `cuda` (today's), `cpu` (torch
  CPU wheels, about 200 MB) and `rocm` (AMD GPUs on Linux), as uv extras with per-platform
  index pins, still hash-locked and wheels only. `install.sh --with-transcription[=cuda|cpu|rocm]`
  picks one; with no value it picks from the detected hardware.
- The CPU engine path is measured and tuned: int8 dynamic quantization of the linear layers,
  bf16 where the CPU supports it, thread count from the core count, batch size chosen by
  memory. Accuracy is compared against the GPU output on the same recordings before any
  optimization is kept.
- The user is told what to expect: doctor reports the installed profile and whether the
  hardware matches it; the welcome screen and the recording list say "about N minutes per hour
  of audio on this computer" from a measurement made at first transcription.
- The queue is unchanged. Long CPU jobs are already resumable and cancellable.

## Capabilities

### Modified Capabilities
- `installation`: compute profiles.
- `transcription`: CPU and ROCm devices as supported, with stated speed.

## Impact

`pyproject.toml`, `uv.lock`, `install.sh`, `doctor.py`, `features.py`, `worker/asr.py`,
`settings.py` (measured speed), welcome and list UI text, README requirements.

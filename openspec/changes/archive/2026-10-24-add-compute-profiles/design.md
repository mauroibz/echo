# Design

## Context

The `EngineLike` protocol already isolates the model from the worker loop, and `Engine` has a
`use_gpu=False` path (float32, batch 1). torch publishes CPU-only and ROCm wheels on its own
indexes, which uv can pin per extra and per platform while keeping one lockfile.

## Goals / Non-Goals

**Goals:** one lockfile, three profiles, every profile resolvable on every supported platform
it applies to; the best possible result from the current model on each device.

**Non-Goals:** other ASR models or engines (deferred, by decision); automatic switching between
profiles after install; AMD GPUs on Windows (PyTorch support is immature; revisit later).

## Decisions

### Extras and indexes

```toml
[project.optional-dependencies]
cuda = ["torch>=2.10", "transformers>=5.12", "peft>=0.19", "silero-vad>=6.2"]
cpu  = [same]
rocm = [same]

[tool.uv]
conflicts = [[{ extra = "cuda" }, { extra = "cpu" }, { extra = "rocm" }]]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[[tool.uv.index]]
name = "pytorch-rocm"
url = "https://download.pytorch.org/whl/rocmX.Y"
explicit = true

[tool.uv.sources]
torch = [
  { index = "pytorch-cpu", extra = "cpu" },
  { index = "pytorch-rocm", extra = "rocm", marker = "sys_platform == 'linux'" },
]
```

`cuda` keeps PyPI. The `worker` extra name is retired; `.install-profile` gains the value
(`full` is read as `cuda` for existing installs). `features.transcription_installed()` is
unchanged; a new `features.compute_profile()` reads the profile file.

### Hardware detection in the installer

Without a value, `--with-transcription` picks `cuda` if `nvidia-smi` or `/proc/driver/nvidia`
exists, `rocm` if `/dev/kfd` exists, else `cpu`, and says which it chose and how to override.

### CPU engine

In `Engine.load()` when the device is CPU: `torch.ao.quantization.quantize_dynamic` on
`nn.Linear` with int8 weights; bf16 autocast if `torch.cpu._is_avx512_bf16_supported()` (or
the equivalent capability check in the pinned torch); threads = physical cores; batch size 2
to 4 depending on available RAM (the model is 8 GB in float32, 2 GB of weights after int8).
Each optimization is kept only if word agreement with the GPU output on the same three
recordings stays above 99%; the numbers go in `docs/design.md` next to the GPU ones.

### Telling the user

The worker records the measured speed (seconds of audio per second) into
`~/.local/state/echo/speed.json` after each job. The list shows the estimate it already
computes; the welcome screen and doctor show "about N min per hour of audio" from the file,
or the profile's expected range before the first job.

## Risks

- ROCm wheel availability for CPython 3.14 lags CUDA; if the pinned torch has no ROCm 3.14
  wheel the `rocm` extra waits for the next torch release, with the others shipped.
- int8 may hurt the adapter more than the base model; the agreement check covers it.

## Decisions made while implementing

- **Profile detection** reads torch's version tag through `importlib.metadata` (`+cpu`,
  `+rocm7.2`, none for PyPI's CUDA build) instead of `.install-profile`, because the package is
  what actually runs even after a manual `uv sync`. `.install-profile` is still written and read
  by the installer; `full` is read as `cuda`.
- **ROCm index** is `rocm7.2`, the build PyTorch publishes for torch 2.14 on CPython 3.14.
  torch 2.14's ROCm wheel depends on `triton-rocm`, which only that index has, so it is listed
  in the `rocm` extra with an index source (uv requires a source restricted to an extra to be
  named in that extra). Without it the resolver backtracked through every older torch.
- **Verification of 1.1**: `uv export --extra cuda` is identical to the old `--extra worker`
  export (60 packages). The `cpu` profile was installed by `./install.sh
  --with-transcription=cpu` in an `ubuntu:24.04` container: torch `2.14.1+cpu`, a 1.2 GB
  environment instead of 5.6 GB, profile read back as `cpu`, doctor warning about the NVIDIA
  GPU it could see. `rocm` resolves; it was not installed (no AMD GPU here).
- **Measurement (2.1, 2.2)** on a 6-core Ryzen 5 7600X rather than an 8-core machine (the
  one available), with the user's own 6.4-minute recording and LibriVox audiobook chapters
  (Galdós, "Miau", public domain) for 20.7 and 62.3 minutes; numbers in `docs/design.md`.
  Thread count: physical cores (6) beat 11 threads for float32, 5.4× against 4.6×.
- **Chosen CPU configuration**: int8 dynamic quantization of every `nn.Linear` except the LoRA
  layers (PEFT reads `lora_A.weight.dtype`, which a quantized layer no longer has), batch 4.
  It is the fastest configuration over the 99% bar on all three recordings (99.02% at worst).
  bf16 also passes, at 99.96% or better and about half the speed; it is documented as the
  alternative but not used, since the spec asks for the fastest passing configuration.
- **Batch size** by `MemAvailable`: 4 from 6 GB free, 2 from 3 GB, else 1. A `MemoryError` or
  an allocator failure halves the batch like a GPU out-of-memory, and at batch 1 fails with a
  CPU-worded message.
- **Speed file**: the last ten jobs per key (`cuda`, `rocm`, or `cpu` whenever the model ran on
  the processor), model load and speech detection included; resumed jobs are not recorded.
  The estimate before any job is 1 minute per hour (GPU) and 5 (CPU), from the measurement.
- **2.4**: no AMD GPU was available; the README says the `rocm` profile is untested.

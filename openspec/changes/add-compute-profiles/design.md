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

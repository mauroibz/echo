# Tasks

## 1. Profiles

- [x] 1.1 Replace the `worker` extra with `cuda`, `cpu`, `rocm` extras, uv conflicts and per-extra index sources; `uv lock`; verify each extra resolves on linux x86-64 and that `cuda` resolves identically to today
- [x] 1.2 `install.sh`: `--with-transcription[=cuda|cpu|rocm]`, hardware detection, profile file migration from `full`; `uninstall.sh` unchanged
- [x] 1.3 `features.compute_profile()`; doctor reports profile and hardware match with the fix for a mismatch; tests

## 2. CPU engine

- [x] 2.1 Measure the current CPU path on an 8-core machine with three recordings (5, 20, 60 min): speed and word agreement with the GPU output; record in `docs/design.md` (needs hardware: GPU and the downloaded model)
- [x] 2.2 Add int8 dynamic quantization and bf16 autocast behind the CPU device; re-measure; keep what passes the 99% agreement bar (needs hardware: GPU and the downloaded model)
- [x] 2.3 Thread and batch-size selection from cores and free memory; OOM handling on CPU (`MemoryError`) mapped to the existing not-enough-memory path with CPU wording
- [x] 2.4 Verify on an AMD GPU with the `rocm` profile if a machine is available; otherwise document the profile as untested in README (needs hardware: GPU and the downloaded model)

## 3. Telling the user

- [x] 3.1 Worker writes `speed.json` after each job; doctor, welcome screen and the list's estimate read it
- [x] 3.2 README requirements rewritten: NVIDIA, AMD (Linux) or CPU, with expected speeds

"""What this install can do. Cheap checks, safe to call from the UI thread."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import shutil
from functools import cache

from . import settings

BASE, CUDA, CPU, ROCM = "base", "cuda", "cpu", "rocm"
PROFILE_LABELS = {CUDA: "NVIDIA GPU (CUDA)", CPU: "processor (CPU)", ROCM: "AMD GPU (ROCm)"}


@cache
def transcription_installed() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers", "peft", "silero_vad"))


def auto_transcribe() -> bool:
    cfg, _ = settings.load()
    return cfg.auto_transcribe and transcription_installed()


@cache
def compute_profile() -> str:
    """The installed transcription profile, read from torch's version without importing it.

    The PyTorch indexes tag their builds ("2.14.1+cpu", "2.14.1+rocm7.2"); PyPI's build, which
    bundles CUDA on Linux and Windows, has no tag. The installed package is the truth even when
    someone ran `uv sync` by hand, so this does not trust `.install-profile`.
    """
    if not transcription_installed():
        return BASE
    try:
        version = importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        return BASE
    local = version.partition("+")[2]
    if local.startswith("rocm"):
        return ROCM
    if local == "cpu":
        return CPU
    return CUDA


def detected_hardware() -> str:
    """The profile the hardware calls for, by the same rules as install.sh."""
    if shutil.which("nvidia-smi") or os.path.exists("/proc/driver/nvidia"):
        return CUDA
    if os.path.exists("/dev/kfd"):
        return ROCM
    return CPU

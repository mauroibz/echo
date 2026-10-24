"""Pinned model revisions. Changing a revision is a deliberate, reviewed edit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelRef:
    repo: str
    revision: str
    required: tuple[str, ...]  # files that must be present in the snapshot
    approx_bytes: int


BASE = ModelRef(
    repo="CohereLabs/cohere-transcribe-03-2026",
    revision="d552dadc2922ba6f6c1f994f8db904d52dcaf942",
    required=("config.json", "model.safetensors", "preprocessor_config.json",
              "processor_config.json", "tokenizer.json", "tokenizer_config.json",
              "generation_config.json"),
    approx_bytes=4_200_000_000,
)
ADAPTER = ModelRef(
    repo="surus-ai/cohere-transcribe-spanish-MegaASR",
    revision="8346c73a9e5a25e815bdbd50853556087359eea6",
    required=("adapter_config.json", "adapter_model.safetensors"),
    approx_bytes=56_000_000,
)
ALL = (BASE, ADAPTER)

# Only data files: never download the repos' Python code, assets or demos.
ALLOW_PATTERNS = ["*.json", "*.safetensors", "tokenizer.model"]


def hf_home() -> Path:
    return Path(os.environ.get("HF_HOME") or Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "huggingface")


def hf_token_present() -> bool:
    return bool(os.environ.get("HF_TOKEN")) or (hf_home() / "token").is_file()


def snapshot_dir(ref: ModelRef) -> Path:
    hub = Path(os.environ.get("HF_HUB_CACHE") or hf_home() / "hub")
    return hub / ("models--" + ref.repo.replace("/", "--")) / "snapshots" / ref.revision


def is_cached(ref: ModelRef) -> bool:
    d = snapshot_dir(ref)
    return all((d / f).exists() for f in ref.required)


def all_cached() -> bool:
    return all(is_cached(r) for r in ALL)


def download(progress=None) -> None:
    """Download the pinned snapshots. Requires the worker profile (huggingface_hub)."""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download

    for ref in ALL:
        if progress:
            progress(f"Downloading {ref.repo}")
        snapshot_download(ref.repo, revision=ref.revision, allow_patterns=ALLOW_PATTERNS)

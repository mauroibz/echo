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
    # Only data files: never the repos' Python code, assets or demos.
    allow: tuple[str, ...] = ("*.json", "*.safetensors", "tokenizer.model")


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
# Speaker embeddings for labeling who speaks (WeSpeaker ResNet34 trained on VoxCeleb, Apache-2.0),
# run on the processor with onnxruntime. Optional: transcription works without it.
SPEAKER = ModelRef(
    repo="Wespeaker/wespeaker-voxceleb-resnet34",
    revision="ff1ac5bca8ef11e90662b879aa923979e0bd277b",
    required=("voxceleb_resnet34.onnx",),
    approx_bytes=26_534_127,
    allow=("voxceleb_resnet34.onnx", "config.yaml"),
)
# Speaker segmentation for finding where someone else speaks inside a passage (pyannote's
# segmentation-3.0, MIT, as exported to ONNX by onnx-community; the original repository is gated,
# this export is not), run on the processor with onnxruntime. Optional like SPEAKER.
SEGMENTATION = ModelRef(
    repo="onnx-community/pyannote-segmentation-3.0",
    revision="733a93b6473d019a773298e08cefa686894b1854",
    required=("onnx/model.onnx",),
    approx_bytes=5_986_908,
    allow=("onnx/model.onnx", "config.json"),
)
ALL = (BASE, ADAPTER)  # needed to transcribe
OPTIONAL = (SPEAKER, SEGMENTATION)

# Languages the pinned processor accepts (transformers' cohere_asr LANGUAGES). The tokenizer has
# language tokens for many more, but the processor refuses them; tests/test_languages.py checks
# that this copy matches the installed processor. Kept here so the window, which never imports
# torch or transformers, can list them.
PROCESSOR_LANGUAGES = ("ar", "de", "el", "en", "es", "fr", "it", "ja", "ko", "nl", "pl", "pt", "vi", "zh")
LANGUAGE_NAMES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "it": "Italian",
                  "de": "German", "nl": "Dutch", "pl": "Polish", "el": "Greek", "ar": "Arabic", "ja": "Japanese",
                  "ko": "Korean", "zh": "Chinese", "vi": "Vietnamese"}
DEFAULT_LANGUAGE = "es"



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


def speaker_cached() -> bool:
    """Both speaker models are downloaded (the welcome screen and doctor offer the rest)."""
    return all(is_cached(r) for r in OPTIONAL)


def speaker_download_mb() -> int:
    """Size of the speaker models still to download, in MB."""
    return round(sum(r.approx_bytes for r in OPTIONAL if not is_cached(r)) / 1e6)


def missing() -> list[ModelRef]:
    return [r for r in (*ALL, *OPTIONAL) if not is_cached(r)]


def download(progress=None, refs=None) -> None:
    """Download the pinned snapshots that are missing. Requires a transcription profile."""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download

    for ref in refs if refs is not None else missing():
        if progress:
            progress(f"Downloading {ref.repo}")
        snapshot_download(ref.repo, revision=ref.revision, allow_patterns=list(ref.allow))


def supported_languages() -> list[str]:
    """Language codes the model can transcribe: its tokenizer's language tokens that the processor
    accepts, Spanish first, then by name. Without the downloaded model, the processor's list."""
    import json
    import re

    codes = set(PROCESSOR_LANGUAGES)
    try:
        with open(snapshot_dir(BASE) / "tokenizer.json", encoding="utf-8") as f:
            tokens = {t.get("content", "") for t in json.load(f).get("added_tokens", [])}
        codes &= {m[2:4] for m in tokens if re.fullmatch(r"<\|[a-z]{2}\|>", m)}
    except (OSError, ValueError):
        pass
    return sorted(codes, key=lambda c: (c != DEFAULT_LANGUAGE, language_name(c)))


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)

"""What this install can do. Cheap checks, safe to call from the UI thread."""

from __future__ import annotations

import importlib.util
from functools import cache

from . import settings


@cache
def transcription_installed() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers", "peft", "silero_vad"))


def auto_transcribe() -> bool:
    cfg, _ = settings.load()
    return cfg.auto_transcribe and transcription_installed()

"""Speech detection and recognition. The only module that touches torch and the model."""

from __future__ import annotations

import logging
import os
from typing import Callable

import numpy as np

from .. import models

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
LANGUAGE = "es"

# Text placed in the decoder's context slot for every passage. Without it the model sometimes
# drops into an unpunctuated, lower-case style for whole passages (48 of 102 passages in one
# test chapter); with it, 47 of those 48 come out punctuated, while clean passages stay
# unchanged (99.8% word agreement over a 20-minute chapter). Measured 2026-10-23.
STYLE_CONTEXT = ("El texto que sigue está escrito en español correcto, con mayúsculas, tildes y "
                 "signos de puntuación.")


def build_context(extra: str | None) -> str:
    """Caller-provided context (e.g. a sentence naming known people and terms), then the style primer.

    Order matters: with terms appended after the primer the model returned nothing on one test
    clip; with the terms sentence first it transcribed correctly and used the terms.
    """
    return f"{extra.strip()} {STYLE_CONTEXT}" if extra and extra.strip() else STYLE_CONTEXT


def min_words(seconds: float) -> int:
    """Fewest words a passage of speech this long should produce (very conservative)."""
    return 1 if seconds < 2.5 else int(seconds * 0.4)


class ModelsMissing(RuntimeError):
    pass


class NotEnoughMemory(RuntimeError):
    pass


OOM_MESSAGE = ("Not enough GPU memory for the transcription model (it needs about 5 GB free). "
               "Close other programs that use the GPU and try again.")


def is_oom(e: BaseException) -> bool:
    """CUDA out-of-memory arrives as OutOfMemoryError or as a generic AcceleratorError."""
    return e.__class__.__name__ == "OutOfMemoryError" or "out of memory" in str(e).lower()


def _quiet_libraries() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ["HF_HUB_OFFLINE"] = "1"  # never touch the network at run time
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    from transformers.utils import logging as hf_logging

    hf_logging.set_verbosity_error()
    hf_logging.disable_progress_bar()


def _feature_extractor(config: dict):
    """The stock CohereAsr feature extractor, with its mel filterbank built without librosa.

    transformers' mel_filter_bank with Slaney scale and norm reproduces librosa.filters.mel to
    within float32 precision (max abs difference 4e-9, verified), so the model sees identical input.
    """
    import torch
    from transformers.audio_utils import mel_filter_bank
    from transformers.feature_extraction_sequence_utils import SequenceFeatureExtractor
    from transformers.models.cohere_asr.feature_extraction_cohere_asr import CohereAsrFeatureExtractor

    class FeatureExtractor(CohereAsrFeatureExtractor):
        def __init__(self, feature_size=128, sampling_rate=16000, hop_length=160, n_fft=512,
                     win_length=400, preemphasis=0.97, padding_value=0.0, dither=1e-5,
                     max_audio_clip_s=35.0, overlap_chunk_second=5.0, min_energy_window_samples=1600,
                     **kwargs):
            SequenceFeatureExtractor.__init__(self, feature_size=feature_size, sampling_rate=sampling_rate,
                                              padding_value=padding_value, **kwargs)
            self.hop_length = hop_length
            self.n_fft = n_fft
            self.win_length = win_length
            self.preemphasis = preemphasis
            self.dither = dither
            self.max_audio_clip_s = max_audio_clip_s
            self.overlap_chunk_second = overlap_chunk_second
            self.min_energy_window_samples = min_energy_window_samples
            mel = mel_filter_bank(num_frequency_bins=n_fft // 2 + 1, num_mel_filters=feature_size,
                                  min_frequency=0.0, max_frequency=sampling_rate / 2,
                                  sampling_rate=sampling_rate, norm="slaney", mel_scale="slaney")
            self.mel_filters = torch.from_numpy(mel.T.astype(np.float32))

    cfg = {k: v for k, v in config.items() if k not in ("feature_extractor_type", "processor_class", "auto_map")}
    # The hub config uses NeMo-style names; map the ones that matter.
    if "n_window_size" in cfg:
        cfg["win_length"] = cfg.pop("n_window_size")
    if "n_window_stride" in cfg:
        cfg["hop_length"] = cfg.pop("n_window_stride")
    return FeatureExtractor(**cfg)


class Engine:
    """Loads lazily; holds the model on the GPU until the worker exits."""

    def __init__(self, use_gpu: bool = True):
        self.use_gpu = use_gpu
        self._model = None
        self._peft = None
        self._processor = None
        self._vad = None
        self.device = "cpu"
        self.batch_size = 8

    # ---- loading ----
    def load(self) -> None:
        if self._model is not None:
            return
        missing = [r.repo for r in models.ALL if not models.is_cached(r)]
        if missing:
            raise ModelsMissing("The transcription model is not downloaded yet. "
                                "Download it from the welcome screen or run: echo-app models download")
        _quiet_libraries()
        import json

        import torch
        from transformers import AutoTokenizer, CohereAsrForConditionalGeneration
        from transformers.models.cohere_asr.processing_cohere_asr import CohereAsrProcessor

        base = models.snapshot_dir(models.BASE)
        with open(base / "preprocessor_config.json") as f:
            fe = _feature_extractor(json.load(f))
        tokenizer = AutoTokenizer.from_pretrained(base)
        self._processor = CohereAsrProcessor(feature_extractor=fe, tokenizer=tokenizer)
        cuda = self.use_gpu and torch.cuda.is_available()
        self.device = "cuda" if cuda else "cpu"
        dtype = torch.bfloat16 if cuda else torch.float32
        try:
            model = CohereAsrForConditionalGeneration.from_pretrained(
                base, dtype=dtype, attn_implementation="sdpa", use_safetensors=True)
            model.to(self.device).eval()
            from peft import PeftModel

            peft = PeftModel.from_pretrained(model, models.snapshot_dir(models.ADAPTER)).eval()
        except Exception as e:
            if is_oom(e):
                self._release()
                raise NotEnoughMemory(OOM_MESSAGE) from e
            raise
        self._model, self._peft = model, peft
        if not cuda:
            torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))
            self.batch_size = 1
        log.info("model loaded on %s", self.device)

    def _release(self) -> None:
        import gc

        import torch

        self._model = self._peft = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @property
    def adapter_available(self) -> bool:
        return self._peft is not None

    # ---- speech detection ----
    def speech_regions(self, audio: np.ndarray, progress: Callable[[float], None] | None = None) -> list[tuple[float, float]]:
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        if self._vad is None:
            self._vad = load_silero_vad(onnx=False)
            torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2) - 1)))
        wav = torch.from_numpy(audio.astype(np.float32) / 32768.0)

        def cb(pct):
            if progress:
                progress(float(pct) / 100.0)

        ts = get_speech_timestamps(wav, self._vad, sampling_rate=SAMPLE_RATE, return_seconds=False,
                                   min_silence_duration_ms=300, speech_pad_ms=100, threshold=0.4,
                                   progress_tracking_callback=cb)
        return [(t["start"] / SAMPLE_RATE, t["end"] / SAMPLE_RATE) for t in ts]

    # ---- recognition ----
    def transcribe(self, clips: list[np.ndarray], adapter: bool = True, context: str | None = None) -> list[str]:
        """Transcribe int16 16 kHz clips (each at most ~30 s).

        A passage whose text is implausibly short for its length is retried with simpler
        context, keeping the fullest result, so a context quirk can never silently drop speech.
        """
        texts = self._transcribe_batch(clips, adapter, context)
        short = [i for i, (c, t) in enumerate(zip(clips, texts)) if len(t.split()) < min_words(len(c) / SAMPLE_RATE)]
        for fallback in ((None, False), (None, True)) if short else ():
            extra, bare = fallback
            if not short:
                break
            retry = self._transcribe_batch([clips[i] for i in short], adapter, extra, bare=bare)
            still = []
            for i, t in zip(short, retry):
                if len(t.split()) > len(texts[i].split()):
                    log.info("passage retried with %s context: %d -> %d words", "no" if bare else "style-only",
                             len(texts[i].split()), len(t.split()))
                    texts[i] = t
                if len(texts[i].split()) < min_words(len(clips[i]) / SAMPLE_RATE):
                    still.append(i)
            short = still
        return texts

    def _transcribe_batch(self, clips: list[np.ndarray], adapter: bool, context: str | None,
                          bare: bool = False) -> list[str]:
        """Halves the batch on GPU out-of-memory."""
        import torch

        self.load()
        try:
            return self._run(clips, adapter, context, bare)
        except Exception as e:
            if not is_oom(e):
                raise
            torch.cuda.empty_cache()
            if len(clips) == 1:
                raise NotEnoughMemory(OOM_MESSAGE) from e
            mid = len(clips) // 2
            self.batch_size = max(1, mid)
            log.warning("GPU out of memory; batch size now %d", self.batch_size)
            return (self._transcribe_batch(clips[:mid], adapter, context, bare)
                    + self._transcribe_batch(clips[mid:], adapter, context, bare))

    def _run(self, clips: list[np.ndarray], adapter: bool, context: str | None, bare: bool = False) -> list[str]:
        import contextlib

        import torch

        audio = [c.astype(np.float32) / 32768.0 for c in clips]
        inputs = self._processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", language=LANGUAGE)
        inputs.pop("audio_chunk_index", None)
        prompt = inputs["decoder_input_ids"]
        context = None if bare else build_context(context)
        if context:
            ctx = self._processor.tokenizer.encode(context, add_special_tokens=False)
            row = prompt[0].tolist()
            row = row[:2] + ctx + row[2:]  # between <|startofcontext|> and <|startoftranscript|>
            prompt = torch.tensor([row] * prompt.shape[0])
            inputs["decoder_input_ids"] = prompt
        prompt_len = prompt.shape[1]
        inputs = {k: (v.to(self.device, dtype=self._model.dtype) if v.is_floating_point() else v.to(self.device))
                  for k, v in inputs.items()}
        longest = max(len(c) for c in clips) / SAMPLE_RATE
        max_new = min(900, int(longest * 12) + 32)
        # PEFT injects LoRA layers into the base model in place, so "no adapter" must go through
        # disable_adapter() rather than calling the base model directly.
        if self._peft is None:
            model, guard = self._model, contextlib.nullcontext()
        elif adapter:
            model, guard = self._peft, contextlib.nullcontext()
        else:
            model, guard = self._peft, self._peft.disable_adapter()
        with torch.inference_mode(), guard:
            out = model.generate(**inputs, max_new_tokens=max_new)
        texts = self._processor.decode(out[:, prompt_len:], skip_special_tokens=True)
        return [t.strip() for t in texts]

    def model_info(self, adapter: bool) -> dict:
        return {"style_context": STYLE_CONTEXT,"base": f"{models.BASE.repo}@{models.BASE.revision}",
                "adapter": f"{models.ADAPTER.repo}@{models.ADAPTER.revision}" if adapter and self.adapter_available else None,
                "adapter_enabled": bool(adapter and self.adapter_available),
                "device": self.device}

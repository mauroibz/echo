"""Speech detection and recognition. The only module that touches torch and the model."""

from __future__ import annotations

import logging
import os
import re
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
STYLE_CONTEXTS = {
    "es": "El texto que sigue está escrito en español correcto, con mayúsculas, tildes y signos de puntuación.",
    "en": "The following text is written in correct English, with capital letters and punctuation.",
}
STYLE_CONTEXT = STYLE_CONTEXTS["es"]
NO_SPACE_LANGUAGES = {"ja", "zh"}  # written without spaces between words


def build_context(extra: str | None, language: str = LANGUAGE) -> str | None:
    """Caller-provided context (e.g. a sentence naming known people and terms), then the style primer.

    Order matters: with terms appended after the primer the model returned nothing on one test
    clip; with the terms sentence first it transcribed correctly and used the terms. Languages
    without a style sentence get the caller's context alone.
    """
    style = STYLE_CONTEXTS.get(language)
    parts = [p for p in ((extra or "").strip(), style) if p]
    return " ".join(parts) or None


def word_count(text: str, language: str = LANGUAGE) -> int:
    """Words in a passage; for Chinese and Japanese, about one word per two characters."""
    if language in NO_SPACE_LANGUAGES:
        return len("".join(text.split())) // 2
    return len(text.split())


# A passage whose mean token log-probability falls below this is retried like a short one.
# Measured 2026-10-24: ordinary passages ranged from -0.01 to -0.17 on an audiobook and on a
# desk microphone; a passage the dictionary's context sentence turned into a hallucinated
# fragment ("Debido a que no se puede" for a sentence of eight seconds) scored -1.17.
RETRY_BELOW_LOGPROB = -0.5


def min_words(seconds: float) -> int:
    """Fewest words a passage of speech this long should produce (very conservative)."""
    return 1 if seconds < 2.5 else int(seconds * 0.4)


# The same one to three words said six or more times running: the model stuck in a loop. Seen
# 2026-10-28 in a meeting: one word and a period forty times, where another run wrote the
# sentence it began; and an unsure passage retried into "Y, y, y, y, …", which the retry kept for being more
# confident and no shorter. Real speech repeats less ("sí, sí, sí", "no, no, no, no").
LOOP = re.compile(r"((?:\b\w+\b[\s,.;:!?¿¡…-]*){1,3}?)\1{5,}", re.IGNORECASE)


def looping(text: str) -> bool:
    return LOOP.search(text) is not None


def unloop(text: str) -> str:
    """A loop cut down to two of its repetitions."""
    return LOOP.sub(lambda m: m.group(0)[:2 * len(m.group(1))], text).strip()


class ModelsMissing(RuntimeError):
    pass


class NotEnoughMemory(RuntimeError):
    pass


OOM_MESSAGE = ("Not enough GPU memory for the transcription model (it needs about 5 GB free). "
               "Close other programs that use the GPU and try again.")
CPU_OOM_MESSAGE = ("Not enough memory for the transcription model (it needs about 6 GB free). "
                   "Close other programs and try again.")


def is_oom(e: BaseException) -> bool:
    """CUDA out-of-memory arrives as OutOfMemoryError or as a generic AcceleratorError; on the
    processor it is MemoryError, or a RuntimeError from the allocator."""
    if isinstance(e, MemoryError):
        return True
    msg = str(e).lower()
    return e.__class__.__name__ == "OutOfMemoryError" or "out of memory" in msg or "failed to allocate" in msg


# Measured on a 10 GB card: the model holds 4.4 GB on the GPU with one passage per batch and
# 5.0 GB with eight, and the driver keeps about 0.4 GB of its own. With less free than this, the
# GPU cannot hold the model and the processor transcribes instead.
GPU_MIN_FREE = int(4.8 * 2**30)


def gpu_usable(torch) -> tuple[bool, str]:
    """Whether the GPU can run the model, and why not. bfloat16 needs the hardware support of an
    RTX 30 series (Ampere) card or newer; emulated, it is slower than the processor."""
    if not torch.cuda.is_available():
        return False, "no usable NVIDIA GPU"
    try:
        native = torch.cuda.is_bf16_supported(including_emulation=False)
    except TypeError:  # older torch
        native = torch.cuda.get_device_capability()[0] >= 8
    if not native:
        return False, "the GPU predates the RTX 30 series (no native bfloat16)"
    free, _total = torch.cuda.mem_get_info()
    if free < GPU_MIN_FREE:
        return False, f"only {free / 2**30:.1f} GB of GPU memory is free (the model needs about 5 GB)"
    return True, ""


def physical_cores() -> int:
    """Physical cores: hyperthread siblings share the vector units, so more threads than cores
    is slower (5.4x against 4.6x real time with 6 against 11 threads on a 6-core desktop CPU)."""
    cores = set()
    try:
        with open("/proc/cpuinfo") as f:
            phys = core = None
            for line in f:
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "physical id":
                    phys = value.strip()
                elif key == "core id":
                    core = value.strip()
                elif not key and core is not None:
                    cores.add((phys, core))
                    phys = core = None
            if core is not None:
                cores.add((phys, core))
    except OSError:
        pass
    if cores:
        return len(cores)
    logical = os.cpu_count() or 2
    return max(1, logical // 2 if logical >= 4 else logical)


def available_memory() -> int | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return None


def cpu_batch_size(available: int | None) -> int:
    """Passages per batch on the processor: 4 is fastest (17x against 13.5x real time at 1);
    each extra passage needs roughly 0.5 GB of activations at the 28-second passage limit."""
    if available is None:
        return 2
    if available >= 6_000_000_000:
        return 4
    return 2 if available >= 3_000_000_000 else 1


def quantize_for_cpu(peft_model) -> None:
    """int8 weights for the linear layers, computed per batch (dynamic quantization).

    The LoRA adapter's own small layers stay in float: PEFT reads their weight dtype, and they
    are a negligible part of the work.
    """
    import torch

    spec = {name: torch.ao.quantization.default_dynamic_qconfig for name, m in peft_model.named_modules()
            if isinstance(m, torch.nn.Linear) and "lora_" not in name}
    torch.ao.quantization.quantize_dynamic(peft_model, spec, dtype=torch.qint8, inplace=True)


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
        self.on_processor_because = ""  # why the processor was used although GPU use was asked for
        self.with_scores = True  # mean token log-probability per passage, for low-confidence marking

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
        cuda = False
        if self.use_gpu and torch.cuda.is_available():
            cuda, why = gpu_usable(torch)
            if not cuda:
                self.on_processor_because = why
                log.warning("transcribing on the processor: %s", why)

        def load_on(cuda: bool):
            self.device = "cuda" if cuda else "cpu"
            model = CohereAsrForConditionalGeneration.from_pretrained(
                base, dtype=torch.bfloat16 if cuda else torch.float32, attn_implementation="sdpa",
                use_safetensors=True)
            model.to(self.device).eval()
            from peft import PeftModel

            peft = PeftModel.from_pretrained(model, models.snapshot_dir(models.ADAPTER)).eval()
            if not cuda:
                quantize_for_cpu(peft)
            return model, peft

        try:
            try:
                model, peft = load_on(cuda)
            except Exception as e:
                if not (cuda and is_oom(e)):
                    raise
                # Another program took the GPU memory meanwhile: the processor still works.
                self._release()
                cuda = False
                self.on_processor_because = "the GPU ran out of memory while loading the model"
                log.warning("transcribing on the processor: %s", self.on_processor_because)
                model, peft = load_on(False)
        except Exception as e:
            if is_oom(e):
                self._release()
                raise NotEnoughMemory(OOM_MESSAGE if cuda else CPU_OOM_MESSAGE) from e
            raise
        self._model, self._peft = model, peft
        if not cuda:
            torch.set_num_threads(physical_cores())
            self.batch_size = cpu_batch_size(available_memory())
        log.info("model loaded on %s (batch %d, %d threads)", self.device, self.batch_size, torch.get_num_threads())

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
    def transcribe(self, clips: list[np.ndarray], adapter: bool = True, context: str | None = None,
                   language: str = LANGUAGE) -> list[str]:
        """Transcribe int16 16 kHz clips (each at most ~30 s) in `language`."""
        return [text for text, _flags, _lp in self.transcribe_flagged(clips, adapter, context, language)]

    def transcribe_flagged(self, clips: list[np.ndarray], adapter: bool = True, context: str | None = None,
                           language: str = LANGUAGE) -> list[tuple[str, list[str], float | None]]:
        """(text, flags, mean token log-probability) per clip.

        A passage whose text is implausibly short for its length is retried with simpler
        context, keeping the fullest result, so a context quirk can never silently drop speech.
        Flags say what the user should check: "retried" when the kept text came from such a retry,
        "short" when even the retries stayed short. The Spanish adapter is only applied to Spanish.
        """
        adapter = adapter and language == "es"
        words = lambda t: word_count(t, language)  # noqa: E731
        results = self._transcribe_batch(clips, adapter, context, language=language)
        texts = [t for t, _lp in results]
        logprobs = [lp for _t, lp in results]
        flags: list[list[str]] = [[] for _ in clips]
        short = [i for i, (c, t) in enumerate(zip(clips, texts))
                 if words(t) < min_words(len(c) / SAMPLE_RATE) or looping(t)]
        for fallback in ((None, False), (None, True)) if short else ():
            extra, bare = fallback
            if not short:
                break
            retry = self._transcribe_batch([clips[i] for i in short], adapter, extra, bare=bare, language=language)
            still = []
            for i, (t, lp) in zip(short, retry):
                if not looping(t) and (words(t) > words(texts[i]) or looping(texts[i])):
                    log.info("passage retried with %s context: %d -> %d words", "no" if bare else "style-only",
                             words(texts[i]), words(t))
                    texts[i], logprobs[i] = t, lp
                    if "retried" not in flags[i]:
                        flags[i].append("retried")
                if words(texts[i]) < min_words(len(clips[i]) / SAMPLE_RATE) or looping(texts[i]):
                    still.append(i)
            short = still
        for i in short:
            if looping(texts[i]):
                texts[i] = unloop(texts[i])
                flags[i].append("loop")
            if words(texts[i]) < min_words(len(clips[i]) / SAMPLE_RATE):
                flags[i].append("short")
        # A passage the model was very unsure of may be a fragment the context sentence caused,
        # with enough words to pass the check above: it gets the same retries, and the more
        # confident text is kept.
        unsure = [i for i, lp in enumerate(logprobs) if lp is not None and lp < RETRY_BELOW_LOGPROB]
        for extra, bare in ((None, False), (None, True)) if unsure else ():
            if not unsure:
                break
            retry = self._transcribe_batch([clips[i] for i in unsure], adapter, extra, bare=bare, language=language)
            still = []
            for i, (t, lp) in zip(unsure, retry):
                if lp is not None and lp > logprobs[i] and words(t) >= words(texts[i]) and not looping(t):
                    log.info("unsure passage retried with %s context: %.2f -> %.2f", "no" if bare else "style-only",
                             logprobs[i], lp)
                    texts[i], logprobs[i] = t, lp
                    if "retried" not in flags[i]:
                        flags[i].append("retried")
                if logprobs[i] < RETRY_BELOW_LOGPROB:
                    still.append(i)
            unsure = still
        return list(zip(texts, flags, logprobs))

    def _transcribe_batch(self, clips: list[np.ndarray], adapter: bool, context: str | None,
                          bare: bool = False, language: str = LANGUAGE) -> list[tuple[str, float | None]]:
        """Halves the batch on GPU out-of-memory."""
        import torch

        self.load()
        try:
            return self._run(clips, adapter, context, bare, language)
        except Exception as e:
            if not is_oom(e):
                raise
            if self.device != "cpu":
                torch.cuda.empty_cache()
            if len(clips) == 1:
                raise NotEnoughMemory(OOM_MESSAGE if self.device != "cpu" else CPU_OOM_MESSAGE) from e
            mid = len(clips) // 2
            self.batch_size = max(1, mid)
            log.warning("out of %smemory; batch size now %d", "GPU " if self.device != "cpu" else "",
                        self.batch_size)
            return (self._transcribe_batch(clips[:mid], adapter, context, bare, language)
                    + self._transcribe_batch(clips[mid:], adapter, context, bare, language))

    def _run(self, clips: list[np.ndarray], adapter: bool, context: str | None, bare: bool = False,
             language: str = LANGUAGE) -> list[tuple[str, float | None]]:
        import contextlib

        import torch

        audio = [c.astype(np.float32) / 32768.0 for c in clips]
        inputs = self._processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", language=language)
        inputs.pop("audio_chunk_index", None)
        prompt = inputs["decoder_input_ids"]
        context = None if bare else build_context(context, language)
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
        scores = self.with_scores
        with torch.inference_mode(), guard:
            out = model.generate(**inputs, max_new_tokens=max_new, output_scores=scores,
                                 return_dict_in_generate=scores)
            if not scores:
                texts = self._processor.decode(out[:, prompt_len:], skip_special_tokens=True)
                return [(t.strip(), None) for t in texts]
            # The log-probability of each chosen token, averaged over the passage's real tokens.
            steps = model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)
        gen = out.sequences[:, -steps.shape[1]:]
        special = torch.tensor(self._processor.tokenizer.all_special_ids, device=gen.device)
        real = ~torch.isin(gen, special)
        mean = (steps.float() * real).sum(dim=1) / real.sum(dim=1).clamp(min=1)
        texts = self._processor.decode(out.sequences[:, prompt_len:], skip_special_tokens=True)
        return [(t.strip(), round(float(m), 4)) for t, m in zip(texts, mean.cpu())]

    def model_info(self, adapter: bool, language: str = LANGUAGE) -> dict:
        adapter = adapter and language == "es"
        return {"style_context": STYLE_CONTEXTS.get(language),
                "base": f"{models.BASE.repo}@{models.BASE.revision}",
                "adapter": f"{models.ADAPTER.repo}@{models.ADAPTER.revision}" if adapter and self.adapter_available else None,
                "adapter_enabled": bool(adapter and self.adapter_available),
                "device": self.device}

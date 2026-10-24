"""Who speaks when: a voice embedding per passage, clustered per recording (numpy, onnxruntime).

The embedding model is WeSpeaker's ResNet34 trained on VoxCeleb (models.SPEAKER), exported to
ONNX and run on the processor in every compute profile; it takes Kaldi filterbank features,
computed here as WeSpeaker computes them (80 mel bins over 25 ms Hamming frames every 10 ms,
then the mean removed). Passages already come from speech detection, so labels are per passage:
enough for interviews and meetings, where turns are longer than a passage's few seconds.
"""

from __future__ import annotations

import logging
import math
from typing import Sequence

import numpy as np

from .. import models

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MIN_SECONDS = 1.5  # shorter passages take a neighbor's speaker instead of an embedding of their own
# Two clusters whose centroids are closer than this cosine distance are one speaker. Measured on
# conversations built from nine LibriVox readers, also through one shared degraded channel:
# every threshold from 0.30 to 0.55 found every speaker and assigned 100% of the speech right,
# merging errors began at 0.60, and single-speaker recordings (including a desk-microphone
# monologue) never split even at 0.15. See docs/design.md.
THRESHOLD = 0.4
# A recording's speaker is suggested as a known person when their centroids are at least this
# similar: different chapters by one reader measured 0.956 or more, different readers 0.72 at most.
RECOGNIZE = 0.85
MIN_SPEAKER_SECONDS = 8.0  # a "speaker" with less speech than this joins the nearest other one


# ---- features ---------------------------------------------------------------------------------

def _mel(f):
    return 1127.0 * np.log(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def _mel_banks(num_bins: int = 80, n_fft: int = 512, rate: int = SAMPLE_RATE, low: float = 20.0) -> np.ndarray:
    """Kaldi's triangular mel filters (num_bins, n_fft // 2 + 1), the Nyquist column empty."""
    high = rate / 2
    mel_low, mel_high = _mel(low), _mel(high)
    delta = (mel_high - mel_low) / (num_bins + 1)
    freqs = np.arange(n_fft // 2) * (rate / n_fft)
    mels = _mel(freqs)
    banks = np.zeros((num_bins, n_fft // 2 + 1), dtype=np.float32)
    for b in range(num_bins):
        left, center, right = mel_low + b * delta, mel_low + (b + 1) * delta, mel_low + (b + 2) * delta
        up = (mels - left) / (center - left)
        down = (right - mels) / (right - center)
        banks[b, :n_fft // 2] = np.maximum(0.0, np.minimum(up, down))
    return banks


_BANKS = None
_WINDOW = None


def fbank(samples: np.ndarray, num_bins: int = 80) -> np.ndarray:
    """Log mel filterbank features (frames, num_bins) of int16 16 kHz audio, mean removed.

    Matches torchaudio.compliance.kaldi.fbank(waveform * 32768, num_mel_bins=80, frame_length=25,
    frame_shift=10, dither=0, window_type="hamming") followed by mean normalization.
    """
    global _BANKS, _WINDOW
    if _BANKS is None:
        _BANKS = _mel_banks(num_bins)
        n = np.arange(400)
        _WINDOW = (0.54 - 0.46 * np.cos(2 * math.pi * n / 399)).astype(np.float32)
    x = np.asarray(samples, dtype=np.float32)
    if len(x) < 400:
        return np.zeros((0, num_bins), dtype=np.float32)
    count = 1 + (len(x) - 400) // 160
    idx = np.arange(400)[None, :] + 160 * np.arange(count)[:, None]
    frames = x[idx]
    frames = frames - frames.mean(axis=1, keepdims=True)  # remove the DC offset
    frames = np.concatenate([frames[:, :1] * (1 - 0.97), frames[:, 1:] - 0.97 * frames[:, :-1]], axis=1)
    frames *= _WINDOW
    power = np.abs(np.fft.rfft(frames, n=512, axis=1)) ** 2
    feats = np.log(np.maximum(power.astype(np.float32) @ _BANKS.T, np.finfo(np.float32).eps))
    return feats - feats.mean(axis=0, keepdims=True)


# ---- embeddings ---------------------------------------------------------------------------------

class Embedder:
    def __init__(self):
        self._session = None

    @staticmethod
    def available() -> bool:
        if not models.speaker_cached():
            return False
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return False
        return True

    def load(self):
        if self._session is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4  # leaves the rest of the machine to the recognizer
            path = models.snapshot_dir(models.SPEAKER) / models.SPEAKER.required[0]
            self._session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])

    def embed(self, samples: np.ndarray) -> np.ndarray:
        """A unit-length voice embedding (256) of one passage."""
        self.load()
        feats = fbank(samples)
        out = self._session.run(None, {"feats": feats[None].astype(np.float32)})[0][0]
        return out / max(1e-9, float(np.linalg.norm(out)))


# ---- clustering ---------------------------------------------------------------------------------

def cluster(embs: np.ndarray, threshold: float = THRESHOLD) -> list[int]:
    """Agglomerative clustering on cosine distance between cluster centroids.

    Repeatedly merges the two closest clusters until no two are closer than `threshold`; the
    similarity matrix is updated only for the merged cluster, so it stays fast for hours of
    passages. Returns a cluster index per embedding.
    """
    n = len(embs)
    if n == 0:
        return []
    sums = np.array(embs, dtype=np.float64)
    alive = np.ones(n, dtype=bool)
    owner = list(range(n))
    centroids = sums / np.linalg.norm(sums, axis=1, keepdims=True)
    sim = centroids @ centroids.T
    np.fill_diagonal(sim, -np.inf)
    while alive.sum() > 1:
        i, j = np.unravel_index(np.argmax(sim), sim.shape)
        if 1.0 - sim[i, j] > threshold:
            break
        sums[i] += sums[j]
        alive[j] = False
        sim[j, :] = -np.inf
        sim[:, j] = -np.inf
        owner = [i if o == j else o for o in owner]
        c = sums[i] / np.linalg.norm(sums[i])
        centroids[i] = c
        row = centroids @ c
        row[~alive] = -np.inf
        row[i] = -np.inf
        sim[i, :] = row
        sim[:, i] = row
    return owner


def label(passages: Sequence[tuple[float, float]], embs: dict[int, np.ndarray],
          threshold: float = THRESHOLD) -> tuple[list[int | None], dict[int, list[float]]]:
    """Speaker numbers 1..N per passage (None when nobody could be told apart) and centroids.

    `embs` maps passage index to embedding for passages long enough to have one; the others take
    the previous passage's speaker (or the next one's at the start). Speakers with very little
    speech join the nearest other speaker, and a recording with one speaker gets no labels.
    """
    idx = sorted(embs)
    if not idx:
        return [None] * len(passages), {}
    groups = cluster(np.stack([embs[i] for i in idx]), threshold)
    by_group: dict[int, list[int]] = {}
    for i, g in zip(idx, groups):
        by_group.setdefault(g, []).append(i)
    dur = {g: sum(passages[i][1] - passages[i][0] for i in members) for g, members in by_group.items()}
    centroid = {g: _unit(np.mean([embs[i] for i in members], axis=0)) for g, members in by_group.items()}
    # Fold speakers with little speech into the nearest real one (a cough, a short aside).
    big = [g for g in by_group if dur[g] >= MIN_SPEAKER_SECONDS] or [max(dur, key=dur.get)]
    for g in list(by_group):
        if g not in big:
            target = max(big, key=lambda b: float(centroid[g] @ centroid[b]))
            by_group[target] += by_group.pop(g)
    if len(by_group) < 2:
        return [None] * len(passages), {}
    of: dict[int, int] = {i: g for g, members in by_group.items() for i in members}
    # Number speakers in order of first appearance.
    numbers: dict[int, int] = {}
    for i in sorted(of):
        numbers.setdefault(of[i], len(numbers) + 1)
    out: list[int | None] = [numbers[of[i]] if i in of else None for i in range(len(passages))]
    for i in range(len(out)):  # short passages: the previous speaker
        if out[i] is None and i > 0:
            out[i] = out[i - 1]
    for i in range(len(out) - 1, -1, -1):  # ...or the next one at the very start
        if out[i] is None and i + 1 < len(out):
            out[i] = out[i + 1]
    centroids = {numbers[g]: [round(float(x), 5) for x in
                              _unit(np.mean([embs[i] for i in members], axis=0))]
                 for g, members in by_group.items()}
    return out, centroids


def _unit(v: np.ndarray) -> np.ndarray:
    return v / max(1e-9, float(np.linalg.norm(v)))


def similarity(a, b) -> float:
    return float(_unit(np.asarray(a, dtype=np.float64)) @ _unit(np.asarray(b, dtype=np.float64)))

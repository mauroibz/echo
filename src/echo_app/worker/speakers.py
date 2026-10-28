"""Who speaks when: a voice embedding per passage, clustered per recording (numpy, onnxruntime).

The embedding model is WeSpeaker's ResNet34 trained on VoxCeleb (models.SPEAKER), exported to
ONNX and run on the processor in every compute profile; it takes Kaldi filterbank features,
computed here as WeSpeaker computes them (80 mel bins over 25 ms Hamming frames every 10 ms,
then the mean removed). Labels are per passage. Before recognition, a segmentation model
(models.SEGMENTATION) finds where someone other than a passage's main voice speaks, and the
passage is cut there, so a short interruption becomes a passage of its own.
"""

from __future__ import annotations

import itertools
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
# monologue) never split even at 0.15. On Spanish readers with quick turns 0.4 merged two people
# in three of eight conversations, 0.35 in one. See docs/design.md.
THRESHOLD = 0.35
# A recording's speaker is suggested as a known person when their centroids are at least this
# similar: different chapters by one reader measured 0.956 or more, different readers 0.72 at most.
RECOGNIZE = 0.85
MIN_SPEAKER_SECONDS = 8.0  # a "speaker" with less speech than this joins the nearest other one
MIN_GLIMPSE = 0.4  # an interruption shorter than this has no embedding, too little to tell voices by
# Segmentation (models.SEGMENTATION): someone other than a passage's main voice for this long is
# cut out as an interruption; shorter runs were mostly noise. Spans closer than JOIN are one.
MIN_TURN = 0.4
JOIN = 1.0


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


# ---- segmentation -------------------------------------------------------------------------------

SEG_WINDOW = 10 * SAMPLE_RATE  # the length the model was trained on
SEG_STEP = 270  # samples between output frames
# About 2.5 s, a whole number of frames so the windows' frames line up: four windows see each
# frame. A 5 s hop missed more interruptions.
SEG_HOP = 148 * SEG_STEP
SEG_HALF = 495  # half the receptive field: frame i is centered at i * SEG_STEP + SEG_HALF
SEG_ACTIVE = 0.4  # share of the windows over a frame that must hear a speaker for it to count
# The model's seven classes: nobody, one of three local speakers, or two of them at once.
_POWERSET = ((), (0,), (1,), (2,), (0, 1), (0, 2), (1, 2))


class Segmenter:
    def __init__(self):
        self._session = None

    @staticmethod
    def available() -> bool:
        if not models.is_cached(models.SEGMENTATION):
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
            opts.intra_op_num_threads = 4
            path = models.snapshot_dir(models.SEGMENTATION) / models.SEGMENTATION.required[0]
            self._session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])

    def window(self, samples: np.ndarray) -> np.ndarray:
        """(frames, 3) activity, 0 or 1, of up to three local speakers in at most 10 s of audio."""
        self.load()
        x = np.zeros(SEG_WINDOW, dtype=np.float32)
        x[:len(samples)] = np.asarray(samples[:SEG_WINDOW], dtype=np.float32) / 32768.0
        classes = self._session.run(None, {"input_values": x[None, None]})[0][0].argmax(axis=1)
        act = np.zeros((len(classes), 3), dtype=np.float32)
        for c, members in enumerate(_POWERSET):
            for m in members:
                act[classes == c, m] = 1.0
        return act


def local_activity(window, samples: np.ndarray) -> np.ndarray:
    """(frames, 3) share of windows hearing each local speaker over a clip of any length.

    `window` is Segmenter.window. Windows of 10 s every 2.5 s; local speakers are numbered
    afresh in each window, so each window's are matched to what the earlier ones heard on their
    overlap, choosing the order that agrees most.
    """
    n = len(samples)
    frames = max(0, (n - 2 * SEG_HALF) // SEG_STEP + 1)
    total = np.zeros((frames, 3))
    count = np.zeros(frames)
    if not frames:
        return total
    starts = list(range(0, max(1, n - SEG_WINDOW + 1), SEG_HOP))
    if n > SEG_WINDOW and starts[-1] + SEG_WINDOW < n:
        starts.append(-(-(n - SEG_WINDOW) // SEG_STEP) * SEG_STEP)  # the last window, on a frame
    for start in starts:
        act = window(samples[start:start + SEG_WINDOW])
        f0 = start // SEG_STEP
        act = act[:max(0, min(len(act), frames - f0, (min(n, start + SEG_WINDOW) - start) // SEG_STEP))]
        if not len(act):
            continue
        seen = count[f0:f0 + len(act)] > 0
        if seen.any():
            heard = total[f0:f0 + len(act)][seen] / count[f0:f0 + len(act)][seen][:, None]
            order = max(itertools.permutations(range(3)), key=lambda o: float((heard * act[seen][:, o]).sum()))
            act = act[:, order]
        total[f0:f0 + len(act)] += act
        count[f0:f0 + len(act)] += 1
    seen = count > 0
    total[seen] /= count[seen][:, None]
    return total


def interruptions(activity: np.ndarray, start: float) -> list[tuple[float, float]]:
    """Spans (seconds) where someone other than the main voice of a passage starting at `start`
    speaks for at least MIN_TURN, including over the main voice; spans closer than JOIN are one."""
    if not len(activity):
        return []
    act = activity >= SEG_ACTIVE
    main = int(np.argmax(act.sum(axis=0)))
    other = act[:, [m for m in range(3) if m != main]].any(axis=1)
    spans: list[tuple[float, float]] = []
    i = 0
    while i < len(other):
        if not other[i]:
            i += 1
            continue
        j = i
        while j < len(other) and other[j]:
            j += 1
        if (j - i) * SEG_STEP / SAMPLE_RATE >= MIN_TURN:
            s = start + (i * SEG_STEP + SEG_HALF) / SAMPLE_RATE
            e = start + (j * SEG_STEP + SEG_HALF) / SAMPLE_RATE
            if spans and s - spans[-1][1] < JOIN:
                spans[-1] = (spans[-1][0], e)
            else:
                spans.append((s, e))
        i = j
    return spans


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


def _clusters(passages, embs: dict[int, np.ndarray], idx: list[int], threshold: float) -> list[list[int]]:
    """Passage indices grouped by voice, with speakers of very little speech folded in."""
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
    return list(by_group.values())


def label(passages: Sequence[tuple[float, float]], embs: dict[int, np.ndarray],
          threshold: float = THRESHOLD, tracks: Sequence[int] | None = None,
          interrupting: Sequence[bool] | None = None, glimpses: dict[int, np.ndarray] | None = None,
          ) -> tuple[list[int | None], dict[int, list[float]]]:
    """Speaker numbers 1..N per passage (None when nobody could be told apart) and centroids.

    `embs` maps passage index to embedding for passages long enough to have one; the others take
    the previous passage's speaker (or the next one's at the start). Speakers with very little
    speech join the nearest other speaker, and a recording with one speaker gets no labels.

    `tracks` gives, for a call recording, the track each passage is on (0 the microphone, 1 the
    computer audio). Voices are then clustered within each track, so a voice in the room and a
    voice in the call are never one speaker, the microphone's speakers are numbered first, and a
    short passage takes its speaker from its own track.

    `interrupting` marks passages that segmentation cut out of another voice's speech: they are
    someone other than the voice around them, so one that clustered with that voice, or was
    too short to embed, takes the nearest other speaker on its track, by its embedding or its
    `glimpses` embedding (of less than MIN_SECONDS of audio), or the only other one there is.
    """
    idx = sorted(embs)
    if not idx:
        return [None] * len(passages), {}
    side = list(tracks) if tracks is not None else [0] * len(passages)
    groups: list[list[int]] = []
    for t in sorted({side[i] for i in idx}):
        groups += _clusters(passages, embs, [i for i in idx if side[i] == t], threshold)
    if len(groups) < 2:
        return [None] * len(passages), {}
    of: dict[int, int] = {i: g for g, members in enumerate(groups) for i in members}
    # Number speakers by track, then in order of first appearance.
    numbers: dict[int, int] = {}
    for i in sorted(of, key=lambda i: (side[i], i)):
        numbers.setdefault(of[i], len(numbers) + 1)
    out: list[int | None] = [numbers[of[i]] if i in of else None for i in range(len(passages))]
    # Short passages: the previous speaker on the same track, or the next one's at its start; then,
    # on a track with no voice of its own, its neighbors' on any track.
    last: dict[int, int] = {}
    for i in range(len(out)):
        if out[i] is None:
            out[i] = last.get(side[i])
        if out[i] is not None:
            last[side[i]] = out[i]
    following: dict[int, int] = {}
    for i in range(len(out) - 1, -1, -1):
        if out[i] is None:
            out[i] = following.get(side[i])
        if out[i] is not None:
            following[side[i]] = out[i]
    for i in range(len(out)):
        if out[i] is None and i > 0:
            out[i] = out[i - 1]
    for i in range(len(out) - 1, -1, -1):
        if out[i] is None and i + 1 < len(out):
            out[i] = out[i + 1]
    centroid = {numbers[g]: _unit(np.mean([embs[i] for i in members], axis=0))
                for g, members in enumerate(groups)}
    if interrupting is not None:
        track_of = {numbers[g]: side[members[0]] for g, members in enumerate(groups)}
        glimpses = glimpses or {}
        for i in range(len(out)):
            if not interrupting[i]:
                continue
            # The voice it interrupts: the nearest passage before it that is not an interruption.
            around = [j for j in range(i - 1, -1, -1) if not interrupting[j]][:1] or \
                [j for j in range(i + 1, len(out)) if not interrupting[j]][:1]
            if not around:
                continue
            host = out[around[0]]
            others = [n for n in centroid if n != host and track_of[n] == side[i]]
            if not others or (i in embs and out[i] != host):
                continue
            v = embs.get(i, glimpses.get(i))
            if v is not None:
                out[i] = max(others, key=lambda n: float(v @ centroid[n]))
            elif len(others) == 1:
                out[i] = others[0]
    centroids = {n: [round(float(x), 5) for x in c] for n, c in centroid.items()}
    return out, centroids


def louder_track(stereo: np.ndarray, spans: Sequence[tuple[float, float]], rate: int = SAMPLE_RATE) -> list[int]:
    """For each span of a call's (N, 2) samples, 0 if the microphone is louder over it, else 1.

    With headphones the microphone hears only the room and the computer audio only the call, so
    the louder track says which side spoke; where both talk at once the passage goes to the
    louder of the two.
    """
    out = []
    for start, end in spans:
        part = stereo[int(start * rate):int(end * rate)].astype(np.float64)
        if not len(part):
            out.append(0)
            continue
        rms = np.sqrt(np.mean(part ** 2, axis=0))
        out.append(0 if rms[0] >= rms[1] else 1)
    return out


def _unit(v: np.ndarray) -> np.ndarray:
    return v / max(1e-9, float(np.linalg.norm(v)))


def similarity(a, b) -> float:
    return float(_unit(np.asarray(a, dtype=np.float64)) @ _unit(np.asarray(b, dtype=np.float64)))

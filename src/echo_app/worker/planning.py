"""Turn speech regions into passages the model can transcribe (pure Python, no torch)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

MAX_PASSAGE = 28.0
MIN_PREFERRED = 8.0
PARAGRAPH_PAUSE = 2.0
# Without long pauses (read text, fast talkers) paragraphs would grow without bound.
PARAGRAPH_SOFT_LIMIT = 90.0  # after this much speech, break at the next pause of SOFT_PAUSE
PARAGRAPH_SOFT_PAUSE = 0.5
PARAGRAPH_HARD_LIMIT = 150.0  # always break after this much
SPLIT_SEARCH = 5.0


@dataclass
class Passage:
    start: float
    end: float
    paragraph: bool = False  # starts a new paragraph
    gap_before: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


def _split_long(start: float, end: float, quietest: Callable[[float, float], float] | None) -> list[tuple[float, float]]:
    """Cut one over-long speech region into pieces of at most MAX_PASSAGE."""
    pieces = []
    while end - start > MAX_PASSAGE:
        lo, hi = start + MAX_PASSAGE - SPLIT_SEARCH, start + MAX_PASSAGE
        cut = quietest(lo, hi) if quietest else hi
        cut = min(max(cut, lo), hi)
        pieces.append((start, cut))
        start = cut
    pieces.append((start, end))
    return pieces


def plan(regions: Sequence[tuple[float, float]],
         quietest: Callable[[float, float], float] | None = None) -> list[Passage]:
    """Group speech regions (seconds, sorted) into passages of at most MAX_PASSAGE seconds.

    Among the region boundaries that keep a passage within the limit, the cut goes at the widest
    pause, preferring passages of at least MIN_PREFERRED seconds. `quietest(lo, hi)` returns the
    quietest time in [lo, hi] and is used to split single regions longer than the limit.
    """
    flat: list[tuple[float, float]] = []
    for s, e in regions:
        if e <= s:
            continue
        flat.extend(_split_long(s, e, quietest) if e - s > MAX_PASSAGE else [(s, e)])
    passages: list[Passage] = []
    i = 0
    prev_end = None
    while i < len(flat):
        start = flat[i][0]
        # Candidates: last region index j such that flat[j].end - start <= MAX_PASSAGE
        j = i
        while j + 1 < len(flat) and flat[j + 1][1] - start <= MAX_PASSAGE:
            j += 1
        if j + 1 < len(flat):
            best, best_gap = j, -1.0
            for k in range(i, j + 1):
                gap = flat[k + 1][0] - flat[k][1]
                long_enough = flat[k][1] - start >= MIN_PREFERRED
                score = gap + (1000.0 if long_enough else 0.0)
                if score > best_gap:
                    best, best_gap = k, score
            j = best
        end = flat[j][1]
        gap = 0.0 if prev_end is None else start - prev_end
        paragraph = prev_end is None or gap >= PARAGRAPH_PAUSE
        passages.append(Passage(start, end, paragraph, gap))
        prev_end = end
        i = j + 1
    _limit_paragraphs(passages)
    return passages


def _limit_paragraphs(passages: list[Passage]) -> None:
    length = 0.0
    for p in passages:
        if not p.paragraph:
            if (length >= PARAGRAPH_SOFT_LIMIT and p.gap_before >= PARAGRAPH_SOFT_PAUSE) \
                    or length >= PARAGRAPH_HARD_LIMIT:
                p.paragraph = True
        if p.paragraph:
            length = 0.0
        length += p.duration


def join_text(segments: Sequence[dict], language: str = "es") -> str:
    """Passages joined with a space, or nothing for languages written without spaces; a blank
    line before each paragraph."""
    sep = "" if language in ("ja", "zh") else " "
    paragraphs: list[list[str]] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if seg.get("paragraph") or not paragraphs:
            paragraphs.append([text])
        else:
            paragraphs[-1].append(text)
    return "\n\n".join(sep.join(p) for p in paragraphs)

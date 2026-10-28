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
# Cutting out an interruption (see cut): each cut goes to the quietest point within this much
# outside the span (or 0.1 s inside it), which for an interruption in a pause is the pause.
CUT_SNAP = 0.25
MIN_PIECE = 0.3  # a sliver shorter than this stays with its neighbor


@dataclass
class Passage:
    start: float
    end: float
    paragraph: bool = False  # starts a new paragraph
    gap_before: float = 0.0
    interrupting: bool = False  # cut out of another voice's speech (see cut)

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


def cut(passages: Sequence[Passage], spans: Sequence[Sequence[float]],
        quietest: Callable[[float, float], float] | None = None) -> list[Passage]:
    """Passages cut where someone interrupts: each (start, end) span inside a passage becomes a
    passage of its own marked `interrupting`, the cuts moved to the quietest point nearby."""
    out: list[Passage] = []
    k = 0
    for p in passages:
        while k < len(spans) and spans[k][1] <= p.start:
            k += 1
        inside = []
        j = k
        while j < len(spans) and spans[j][0] < p.end:
            inside.append(spans[j])
            j += 1
        pieces: list[list] = []  # [start, end, interrupting]
        pos = p.start
        for s, e in inside:
            a = min(max(s, p.start), p.end)
            b = min(max(e, p.start), p.end)
            if quietest:
                a = quietest(max(p.start, a - CUT_SNAP), min(p.end, a + 0.1))
                b = quietest(max(a, b - 0.1), min(p.end, b + CUT_SNAP))
            if b - max(a, pos) < MIN_PIECE:
                continue
            if a - pos >= MIN_PIECE:
                pieces.append([pos, a, False])
            elif pieces:
                pieces[-1][1] = max(pos, a)
            else:
                a = pos  # the sliver before it at the passage start goes with it
            pieces.append([max(a, pos), b, True])
            pos = b
        if p.end - pos >= MIN_PIECE or not pieces:
            pieces.append([pos, p.end, False])
        else:
            pieces[-1][1] = p.end
        for n, (s, e, interrupting) in enumerate(pieces):
            out.append(Passage(s, e, p.paragraph if n == 0 else False, p.gap_before if n == 0 else 0.0,
                               interrupting))
    return out


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

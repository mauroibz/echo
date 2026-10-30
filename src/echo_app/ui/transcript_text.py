"""What the transcript panel shows text with: constants, text helpers and passage positions."""

from __future__ import annotations

import unicodedata

from .. import align, transcription
from ..library import Recording

AUTOSAVE_MS = 1000
# Block states marking a linked set's fixed lines: the part's heading, a line saying why it has no
# text yet, and the blank line between parts. Body lines carry no state.
HEAD, LOCK, SEP = 100_000, 200_000, 300_000
NAME_SAMPLE_S = 6.0  # how much of a speaker the naming bar plays: enough to know a voice
REPLAY_AFTER_MS = 1000  # after this long without typing, the passage being corrected plays again
CLICK_LEAD_S = 0.5  # a click in the text starts playback this much before the word, to catch it whole
BASE_MARGIN = 14  # the text's margin inside the editor
HEAD_ROOM = 34  # with a speaker's name over the first paragraph: room above it for the name


def _fold(text: str) -> str:
    """Lower-case, accent-free copy with the same length (for accent-insensitive find)."""
    return "".join((unicodedata.normalize("NFD", c)[0] if c else c).lower() for c in text)


def _plain(text: str) -> str:
    """Text as the editor gives it back: Qt turns non-breaking spaces into spaces, so comparing
    saved text with what the editor holds must do the same (or an untouched text looks edited)."""
    return text.replace("\u00a0", " ")


def _occurrences(hay: str, needle: str) -> list[tuple[int, int]]:
    out, i = [], hay.find(needle)
    while i >= 0:
        out.append((i, i + len(needle)))
        i = hay.find(needle, i + 1)
    return out


def segment_spans(segments: list[dict]) -> list[tuple[int, int, float]]:
    """Character spans of each passage in the joined model text (mirrors planning.join_text)."""
    spans = []
    pos = 0
    first = True
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if not first:
            pos += 2 if seg.get("paragraph") else 1
        spans.append((pos, pos + len(text), float(seg.get("start", 0.0))))
        pos += len(text)
        first = False
    return spans


def _estimate(duration: float | None) -> str:
    """", in about 4 minutes" from the measured speed, for recordings long enough to wait for."""
    minutes, _measured = transcription.minutes_per_hour()
    if not duration or minutes is None:
        return ""
    est = duration / 3600 * minutes
    if est < 1:
        return ""
    return f", in about {round(est)} minute{'s' if round(est) != 1 else ''}"


def flag_reason(flag: str, seg: dict) -> str:
    """Why a passage is marked, in words."""
    seconds = max(0, round(float(seg.get("end", 0)) - float(seg.get("start", 0))))
    return {"short": f"very few words for {seconds} s of speech",
            "retried": "transcribed a second time because the first try came back too short",
            "low": "the model was unsure of it",
            "loop": "the model repeated itself here; listen to it"}.get(flag, flag)


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def segment_offsets(segments: list[dict], language: str = "es") -> dict[int, int]:
    """Character offset of each non-empty segment in the joined text, by segment index."""
    sep = align.separator(language)
    out = {}
    pos = 0
    first = True
    for k, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if not first:
            pos += 2 if seg.get("paragraph") else sep
        # Edit positions refer to the unstripped segment text; the joined text is stripped.
        out[k] = pos - (len(seg.get("text") or "") - len((seg.get("text") or "").lstrip()))
        pos += len(text)
        first = False
    return out


def shown_segments(rec: Recording) -> list[dict]:
    """The model segments with the corrected texts when a corrected copy exists."""
    t = rec.transcript() or {}
    segs = t.get("segments", [])
    c = rec.corrected()
    if c and len(c.get("segments", [])) == len(segs):
        segs = [{**s, "text": tx} for s, tx in zip(segs, c["segments"])]
    return segs

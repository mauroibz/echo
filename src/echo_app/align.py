"""Map the text shown in the editor back onto the model's passages (stdlib only).

The model transcript is a list of timed segments; the user's edited text is free text. To give
edited text passage times (margin, subtitles, follow-along), each segment's first word is found
in the edited text by aligning the two word sequences with difflib. A segment whose first word
was deleted starts at the next word that still matches; a segment with no match left in the
edited text gets an empty span.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def _fold(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c)).casefold()


def _words(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), _fold(m.group())) for m in _WORD.finditer(text)]


def model_spans(segments: list[dict]) -> list[tuple[int, int, int]]:
    """(start, end, segment index) of each non-empty segment in the joined model text, which is
    the passages joined with a space, or a blank line before a paragraph (planning.join_text)."""
    spans = []
    pos = 0
    first = True
    for k, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if not first:
            pos += 2 if seg.get("paragraph") else 1
        spans.append((pos, pos + len(text), k))
        pos += len(text)
        first = False
    return spans


def align(segments: list[dict], text: str) -> list[tuple[int, int, int]]:
    """(start, end, segment index) spans of `text` for every non-empty segment, in order.

    When `text` is the joined model text this is exact; for edited text it follows the words.
    """
    from .worker.planning import join_text

    model_text = join_text(segments)
    spans = model_spans(segments)
    if text == model_text:
        return spans
    mw, ew = _words(model_text), _words(text)
    sm = difflib.SequenceMatcher(None, [w for *_x, w in mw], [w for *_x, w in ew], autojunk=False)
    # For every model word index, the edited word index it matched (if any).
    matched: dict[int, int] = {}
    for a, b, n in sm.get_matching_blocks():
        for i in range(n):
            matched[a + i] = b + i
    # Each segment starts at the edited position of its first model word that still matches.
    starts: list[tuple[int | None, int]] = []
    wi = 0
    for s, e, k in spans:
        while wi < len(mw) and mw[wi][1] <= s:
            wi += 1
        first = wi
        while wi < len(mw) and mw[wi][0] < e:
            wi += 1
        hit = next((matched[i] for i in range(first, wi) if i in matched), None)
        starts.append((ew[hit][0] if hit is not None else None, k))
    # A start that goes backwards (a sentence moved elsewhere) cannot be honored; drop it.
    last = -1
    for n, (pos, k) in enumerate(starts):
        if pos is not None and pos >= last:
            last = pos
        else:
            starts[n] = (None, k)
    # Words added right after a paragraph break belong to the passage after it.
    prev = None
    for n, (pos, k) in enumerate(starts):
        if pos is None:
            continue
        if prev is not None:
            brk = text.rfind("\n\n", prev, pos)
            if brk >= 0:
                after = brk + 2
                while after < pos and text[after].isspace():
                    after += 1
                starts[n] = (after, k)
        prev = starts[n][0]
    known = [n for n, (pos, _k) in enumerate(starts) if pos is not None]
    first_char = next((m.start() for m in re.finditer(r"\S", text)), 0)
    result = []
    for n, (pos, k) in enumerate(starts):
        if pos is None:
            result.append((0, 0, k))
            continue
        j = known.index(n)
        if j == 0:
            pos = min(pos, first_char)  # text added before the first passage belongs to it
        end = starts[known[j + 1]][0] if j + 1 < len(known) else len(text)
        while end > pos and text[end - 1].isspace():
            end -= 1
        result.append((pos, end, k))
    return result


def cues(segments: list[dict], text: str) -> list[tuple[float, float, str, bool, int | None]]:
    """(start s, end s, text, starts a paragraph, speaker number) per passage of `text`, for
    subtitles and exports. Passages whose text the user deleted are left out.
    """
    out = []
    for s, e, k in align(segments, text):
        piece = text[s:e].strip()
        if not piece:
            continue
        seg = segments[k]
        out.append((float(seg.get("start", 0.0)), float(seg.get("end", 0.0)), piece, bool(seg.get("paragraph")),
                    seg.get("speaker")))
    return out

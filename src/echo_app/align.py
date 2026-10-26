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


def separator(language: str) -> int:
    """Characters between passages in the joined text: none for languages written without spaces."""
    return 0 if language in ("ja", "zh") else 1


def model_spans(segments: list[dict], language: str = "es") -> list[tuple[int, int, int]]:
    """(start, end, segment index) of each non-empty segment in the joined model text, which is
    the passages joined with a space (nothing for Chinese and Japanese), or a blank line before a
    paragraph (planning.join_text)."""
    sep = separator(language)
    spans = []
    pos = 0
    first = True
    for k, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if not first:
            pos += 2 if seg.get("paragraph") else sep
        spans.append((pos, pos + len(text), k))
        pos += len(text)
        first = False
    return spans


def align(segments: list[dict], text: str, language: str = "es") -> list[tuple[int, int, int]]:
    """(start, end, segment index) spans of `text` for every non-empty segment, in order.

    When `text` is the joined model text this is exact; for edited text it follows the words.
    """
    from .worker.planning import join_text

    model_text = join_text(segments, language)
    spans = model_spans(segments, language)
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


def speaker_pieces(segments: list[dict], text: str, spans: list[tuple[int, int, int]],
                   fixes: list[dict] | None = None) -> list[tuple[int, int, int, int | None]]:
    """(start, end, segment index, speaker) pieces of `text`: each passage span with its speaker,
    a whole-passage fix replacing it, and a fix's words (`text`) cut out of their passage as a
    piece of their own. Words no longer found in their passage are ignored. Pieces exclude the
    whitespace around them; merges are not resolved here (Recording.speaker does that)."""
    whole = {f["segment"]: f["speaker"] for f in fixes or () if not f.get("text")}
    cuts_of: dict[int, list[dict]] = {}
    for f in fixes or ():
        if f.get("text"):
            cuts_of.setdefault(f["segment"], []).append(f)
    out = []

    def add(a: int, b: int, k: int, who):
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            out.append((a, b, k, who))

    for a, b, k in spans:
        who = whole.get(k, segments[k].get("speaker"))
        cuts = []
        for f in cuts_of.get(k, ()):
            i = text.find(f["text"], a, b)
            if i >= 0:
                cuts.append((i, i + len(f["text"]), f["speaker"]))
        pos = a
        for s, e, sp in sorted(cuts):
            if s < pos:
                continue  # overlaps an earlier cut
            add(pos, s, k, who)
            add(s, e, k, sp)
            pos = e
        add(pos, b, k, who)
    return out


def cues(segments: list[dict], text: str, language: str = "es",
         fixes: list[dict] | None = None) -> list[tuple[float, float, str, bool, int | None]]:
    """(start s, end s, text, starts a paragraph, speaker number) per piece of `text`, for
    subtitles and exports. Passages whose text the user deleted are left out. A passage split by
    a speaker fix gives several pieces, timed by their place in the passage's text (the model
    times passages, not words)."""
    spans = align(segments, text, language)
    span_of = {}
    for a, b, k in spans:  # each passage's text, without the whitespace around it
        piece = text[a:b]
        a += len(piece) - len(piece.lstrip())
        span_of[k] = (a, a + len(piece.strip()))
    out = []
    last_k = None
    for s, e, k, who in speaker_pieces(segments, text, spans, fixes):
        seg = segments[k]
        t0, t1 = float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
        ps, pe = span_of[k]
        if (s, e) != (ps, pe) and pe > ps:  # split by a fix: timed by its place in the passage
            t0, t1 = round(t0 + (t1 - t0) * (s - ps) / (pe - ps), 2), round(t0 + (t1 - t0) * (e - ps) / (pe - ps), 2)
        # A passage starts a paragraph where the model said so; a piece split off it always does.
        out.append((t0, t1, text[s:e], bool(seg.get("paragraph")) if k != last_k else True, who))
        last_k = k
    return out

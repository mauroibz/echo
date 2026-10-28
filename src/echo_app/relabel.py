"""Who said what, again, from the user's "Said by" fixes, without transcribing again.

The worker keeps each passage's voiceprint (the embedding the speakers were clustered from) next
to the transcript. The passages the user fixed say what each person sounds like in this
recording; every other passage goes to the person it sounds closest to. Pure Python: a meeting
has a few hundred voiceprints, and this runs in the window in well under a second.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from .fsutil import atomic_write_json, read_json
from .library import RELABELED, VOICEPRINTS

# Two rounds of k-means from the labels as the user fixed them: each voice is the mean of its
# passages, each passage goes to the nearest voice, then again. A passage only moves when it is
# MARGIN closer to the other voice. Measured on the synthetic conversations of add-speaker-turns
# (see its design.md): describing a voice by its fixed passages alone made things worse, since
# the passages a user fixes are the ones that sound least like the rest of that person.
ROUNDS = 2
MARGIN = 0.1


def _unit(v: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _mean(vs: list[Sequence[float]]) -> list[float]:
    return _unit([sum(col) / len(vs) for col in zip(*vs)])


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def reassign(labels: Sequence[int | None], prints: dict[int, Sequence[float]], anchors: dict[int, int],
             tracks: dict[int, int] | None = None, interrupting: Sequence[int] = ()) -> list[int | None]:
    """New speaker per passage, given the current `labels`, voiceprints by passage, and `anchors`
    (passage -> speaker, the user's fixes), which are kept.

    With `tracks` (speaker -> track of a call) a passage only moves to a speaker on its own track.
    A passage without a voiceprint keeps its speaker, unless it only had it from the passage
    before it (the worker labels short passages that way) and that one moved.
    """
    out: list[int | None] = list(labels)
    for k, n in anchors.items():
        out[k] = n
    track_of = dict(tracks or {})
    for k, n in anchors.items():  # a speaker the user added is on the track of what they fixed
        if n not in track_of and labels[k] in track_of:
            track_of[n] = track_of[labels[k]]
    voiced = [k for k in sorted(prints) if out[k] is not None]
    unit = {k: _unit(prints[k]) for k in voiced}
    for _ in range(ROUNDS):
        groups: dict[int, list] = {}
        for k in voiced:
            groups.setdefault(out[k], []).append(unit[k])
        centers = {n: _mean(vs) for n, vs in groups.items()}
        moved = list(out)
        for k in voiced:
            if k in anchors:
                continue
            home = track_of.get(labels[k]) if labels[k] is not None else None
            allowed = [n for n in centers if tracks is None or track_of.get(n) == home]
            if not allowed:
                continue
            best = max(allowed, key=lambda n: _dot(unit[k], centers[n]))
            here = _dot(unit[k], centers[out[k]]) if out[k] in centers else -1.0
            if _dot(unit[k], centers[best]) - here > MARGIN:
                moved[k] = best
        out = moved
    skip = set(interrupting)
    prev: int | None = None
    for k in range(len(out)):
        if k in unit:
            prev = k
        elif k not in anchors and k not in skip and prev is not None and labels[k] == labels[prev] \
                and labels[k] is not None:
            out[k] = out[prev]
    return out


def voiceprints(rec, transcript: dict | None = None) -> dict | None:
    """The worker's voiceprints for the current transcript, if it kept them."""
    t = transcript if transcript is not None else rec.transcript() or {}
    try:
        data = read_json(rec.path(VOICEPRINTS))
    except (FileNotFoundError, ValueError):
        return None
    return data if data.get("transcript") == t.get("created") else None


def relabel(rec) -> int | None:
    """Reassign the passages of `rec` from its fixes; returns how many changed speaker, or None
    without voiceprints (a transcript from before they were kept: transcribe again). The result is
    a file of its own, read over the model's transcript; `restore` removes it."""
    t = rec.transcript() or {}
    vp = voiceprints(rec, t)
    info = t.get("speakers")
    if vp is None or not info:
        return None
    segs = t.get("segments") or []
    labels = [rec.speaker(s.get("speaker")) for s in segs]
    anchors = {int(f["segment"]): rec.speaker(int(f["speaker"])) for f in rec.fixes(t)
               if not f.get("text") and 0 <= int(f["segment"]) < len(segs)}
    prints = {int(k): v for k, v in (vp.get("passages") or {}).items() if int(k) < len(segs)}
    tracks = {int(k): int(v) for k, v in (info.get("tracks") or {}).items()} or None
    new = reassign(labels, prints, anchors, tracks, vp.get("interrupting") or ())
    changed = sum(1 for k, (a, b) in enumerate(zip(labels, new)) if a != b and k not in anchors)
    by: dict[int, list] = {}
    for k, v in prints.items():
        if new[k] is not None:
            by.setdefault(new[k], []).append(v)
    out: dict[str, Any] = {
        "transcript": t.get("created"), "speakers": new,
        "centroids": {str(n): [round(x, 5) for x in _mean(vs)] for n, vs in sorted(by.items())},
        "count": max([n for n in new if n is not None] + [int(info.get("count") or 0)])}
    if tracks is not None:  # a speaker the user added is on the track of the passages they fixed
        added = {str(n): tracks[labels[k]] for k, n in anchors.items() if n not in tracks and labels[k] in tracks}
        out["tracks"] = {**(info.get("tracks") or {}), **added}
    atomic_write_json(rec.path(RELABELED), out)
    return changed


def restore(rec) -> bool:
    """Back to the speakers the worker found."""
    if not rec.path(RELABELED).exists():
        return False
    rec.path(RELABELED).unlink(missing_ok=True)
    return True


def relabeled(rec) -> bool:
    return bool(((rec.transcript() or {}).get("speakers") or {}).get("relabeled"))

"""One speaker per person: the speakers a recording's labeling found, grouped again (stdlib only).

The worker clusters voices within each track of a call and never across them, and keeps any
"speaker" with 8 s of speech. On real calls without headphones each voice reaches both tracks, so
almost every person came out twice, plus fragments of a few seconds: 3 people became 9 speakers,
6 became 19. Measured on the user's 10 latest calls (centroids only): speakers who are one voice on
both tracks were 0.84 to 0.96 similar, different voices across tracks 0.78 at most.

So after labeling, speakers are joined, as merges the user can undo, when:
- they sound like the same known person (a voice the user named in other recordings),
- they are on different tracks and at least CROSS_TRACK similar,
- they have less than SMALL_SHARE of the speech: they join the nearest other voice.
Speakers the user named differently are never joined. This runs in the worker after labeling and
in the window, once (VERSION), on recordings labeled before it, so no transcription is needed.

Known voices also name speakers: a suggestion ("sounds like Ana") from SUGGEST, and the name itself
when the match is certain (AUTO_NAME, with a voice learned from AUTO_MIN_RECORDINGS recordings).
Measured leave-one-out on the 28 speakers the user had named: the right person was the best match
every time, at 0.74 to 0.95; the best wrong person was at most 0.61. A speaker named this way does
not teach the voice (only the user's own naming does), so one wrong match cannot drift it.
"""

from __future__ import annotations

import math
from typing import Sequence

VERSION = 1
CROSS_TRACK = 0.82  # one voice on both tracks of a call: twins measured 0.84-0.96, others <= 0.78
SMALL_SHARE = 0.015  # a speaker with less of the speech than this (and under a minute) joins the nearest
SMALL_MAX_S = 60.0  # never fold away someone who spoke a minute or more
SUGGEST = 0.75  # "sounds like": the right person measured 0.74-0.95, a wrong one <= 0.61
SUGGEST_MARGIN = 0.10  # ...and this much closer than anyone else
AUTO_NAME = 0.85  # named without asking: certain, and
AUTO_MARGIN = 0.20  # far closer than anyone else, and
AUTO_MIN_RECORDINGS = 2  # a voice the user confirmed in at least this many recordings


def _unit(v: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def similarity(a: Sequence[float], b: Sequence[float]) -> float:
    a, b = _unit(a), _unit(b)
    return sum(x * y for x, y in zip(a, b))


def known_match(centroid: Sequence[float], voices: dict[str, dict], exclude: str = "") \
        -> tuple[str | None, float, float]:
    """The known person `centroid` sounds most like: (name, similarity, lead over the next person).
    `exclude` leaves one recording's part out of each voice (the recording being matched taught it)."""
    scores = []
    for name, v in voices.items():
        voice = v.get("voice") or []
        if len(voice) != len(centroid):
            continue
        part = (v.get("parts") or {}).get(exclude) if exclude else None
        if part is not None and len(part) == len(voice):
            n = int(v.get("recordings", 1))
            if n <= 1:
                continue  # all it knows of this person came from this recording
            voice = [(x * n - y) / (n - 1) for x, y in zip(voice, part)]  # the mean without it
        scores.append((similarity(centroid, voice), name))
    if not scores:
        return None, 0.0, 0.0
    scores.sort(reverse=True)
    best, name = scores[0]
    lead = best - scores[1][0] if len(scores) > 1 else best
    return name, best, lead


def suggestion(centroid, voices: dict[str, dict], exclude: str = "") -> str | None:
    name, score, lead = known_match(centroid, voices, exclude)
    return name if name and score >= SUGGEST and lead >= SUGGEST_MARGIN else None


def certain(centroid, voices: dict[str, dict], exclude: str = "") -> str | None:
    """A known person to name without asking, or None."""
    name, score, lead = known_match(centroid, voices, exclude)
    if not name or score < AUTO_NAME or lead < AUTO_MARGIN:
        return None
    learned = voices[name]
    count = int(learned.get("recordings", 1)) - (1 if exclude in (learned.get("parts") or {}) else 0)
    return name if count >= AUTO_MIN_RECORDINGS else None


def groups(centroids: dict[int, Sequence[float]], tracks: dict[int, int], seconds: dict[int, float],
           names: dict[int, str], voices: dict[str, dict], exclude: str = "") -> list[tuple[int, int]]:
    """The merges (source, target) that make one speaker per person, in order. `centroids`,
    `tracks`, `seconds` and `names` are by speaker after the merges already made; the target of
    each group is its speaker with the most speech (or the one the user named)."""
    members: dict[int, set[int]] = {n: {n} for n in centroids}

    def named(g: int) -> set[str]:
        return {names[m] for m in members[g] if names.get(m)}

    def secs(g: int) -> float:
        return sum(seconds.get(m, 0.0) for m in members[g])

    def centroid(g: int) -> list[float]:
        total = [0.0] * len(centroids[g])
        for m in members[g]:
            w = max(seconds.get(m, 0.0), 1.0)
            total = [t + w * x for t, x in zip(total, _unit(centroids[m]))]
        return _unit(total)

    def join(a: int, b: int) -> bool:
        if len(named(a) | named(b)) > 1:
            return False  # the user said these are different people
        members[a] |= members.pop(b)
        return True

    # Speakers that sound like the same known person.
    by_voice: dict[str, list[int]] = {}
    for n in sorted(centroids):
        who = names.get(n) or suggestion(centroids[n], voices, exclude)
        if who:
            by_voice.setdefault(who, []).append(n)
    for ns in by_voice.values():
        for m in ns[1:]:
            if ns[0] in members and m in members:
                join(ns[0], m)
    # One voice on both tracks of a call, the closest pair first.
    refused: set[tuple[int, int]] = set()
    while True:
        best = None
        ks = sorted(members)
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                if (a, b) in refused or {tracks.get(m) for m in members[a]} == {tracks.get(m) for m in members[b]}:
                    continue
                s = similarity(centroid(a), centroid(b))
                if s >= CROSS_TRACK and (best is None or s > best[0]):
                    best = (s, a, b)
        if best is None:
            break
        if not join(best[1], best[2]):
            refused.add((best[1], best[2]))
    # Fragments: a few seconds of someone in a long call join the nearest voice.
    total = sum(seconds.values())
    least = min(SMALL_MAX_S, SMALL_SHARE * total)  # the worker already folds anyone under 8 s
    big = [g for g in members if secs(g) >= least or named(g)] or [max(members, key=secs)]
    for g in sorted(members):
        if g in big or g not in members:
            continue
        for t in sorted(big, key=lambda b: -similarity(centroid(g), centroid(b))):
            if join(t, g):
                break
    merges = []
    for g, ms in members.items():
        target = next((m for m in sorted(ms, key=lambda m: -seconds.get(m, 0.0)) if names.get(m)), None) or \
            max(ms, key=lambda m: (seconds.get(m, 0.0), -m))
        merges += [(m, target) for m in sorted(ms) if m != target]
    return merges


def apply(rec, voices: dict[str, dict] | None = None) -> tuple[int, list[str]]:
    """Group `rec`'s speakers and name the certain ones; returns (speakers joined, names given).
    Marks the recording so it runs once (a merge the user undoes stays undone)."""
    from . import dictionary

    t = rec.transcript() or {}
    info = t.get("speakers") or {}
    raw = {int(k): v for k, v in (info.get("centroids") or {}).items() if v}
    if rec.meta.speakers_off or len(raw) < 2:
        rec.update(speakers_grouped=VERSION)
        return 0, []
    voices = dictionary.voices() if voices is None else voices
    now = current(rec)  # speakers as they are now: merged ones are one
    centroids = {s: c for s, (c, _secs, _track) in now.items()}
    seconds = {s: secs for s, (_c, secs, _track) in now.items()}
    tracks = {s: track for s, (_c, _secs, track) in now.items()}
    names = {int(k): v for k, v in rec.meta.speakers.items() if v}
    merges = groups(centroids, tracks, seconds, names, voices, exclude=rec.id)
    for source, target in merges:
        rec.merge_speakers(source, target)
    # Name the certain ones, by their voices as joined; their voices are not learned from it.
    given = []
    names = dict(rec.meta.speakers)
    used = set(names.values())
    joined = {s: c for s, (c, _secs, _track) in current(rec).items()}
    for s in sorted(joined):
        if str(s) in names:
            continue
        who = certain(joined[s], voices, exclude=rec.id)
        if who and who not in used:
            names[str(s)] = who
            used.add(who)
            given.append(who)
    by_voice = sorted(set(rec.meta.speakers_by_voice) | {int(k) for k, v in names.items() if v in given})
    rec.update(speakers=names, speakers_grouped=VERSION, speakers_by_voice=by_voice)
    return len(merges), given


def current(rec) -> dict[int, tuple[list[float], float, int]]:
    """Each speaker of `rec` after merges: (centroid weighted by speech, seconds, track)."""
    t = rec.transcript() or {}
    info = t.get("speakers") or {}
    raw = {int(k): v for k, v in (info.get("centroids") or {}).items() if v}
    secs: dict[int, float] = {}
    for sg in t.get("segments") or []:
        n = sg.get("speaker")
        if n is not None and sg.get("text"):
            secs[int(n)] = secs.get(int(n), 0.0) + float(sg.get("end", 0)) - float(sg.get("start", 0))
    tracks = {int(k): int(v) for k, v in (info.get("tracks") or {}).items()}
    by: dict[int, list[int]] = {}
    for n in raw:
        s = rec.speaker(n)
        if s is not None:
            by.setdefault(s, []).append(n)
    out = {}
    for s, ns in by.items():
        total = [0.0] * len(raw[ns[0]])
        for n in ns:
            w = max(secs.get(n, 0.0), 1.0)
            total = [a + w * x for a, x in zip(total, _unit(raw[n]))]
        main = max(ns, key=lambda n: secs.get(n, 0.0))
        out[s] = (_unit(total), sum(secs.get(n, 0.0) for n in ns), tracks.get(main, 0))
    return out


def suggestions(rec, voices: dict[str, dict] | None = None) -> dict[int, str]:
    """Who each unnamed speaker sounds like, from the voices as the user has taught them so far:
    a recording labeled before a voice was learned gets the suggestion too."""
    from . import dictionary

    voices = dictionary.voices() if voices is None else voices
    names = rec.meta.speakers
    used = set(names.values())
    out = {}
    for s, (c, _secs, _track) in current(rec).items():
        if str(s) in names:
            continue
        who = suggestion(c, voices, exclude=rec.id)
        if who and who not in used:
            out[s] = who
    return out


def ranked(rec, n: int, voices: dict[str, dict] | None = None) -> list[str]:
    """Known voices by how much speaker `n` sounds like them, closest first."""
    from . import dictionary

    voices = dictionary.voices() if voices is None else voices
    c = current(rec).get(n)
    if c is None:
        return []
    scored = [(similarity(c[0], v["voice"]), name) for name, v in voices.items()
              if len(v.get("voice") or []) == len(c[0])]
    return [name for _s, name in sorted(scored, reverse=True)]

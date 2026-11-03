"""One speaker per person: speakers grouped again after labeling, and known voices naming them."""

from __future__ import annotations

import json

import numpy as np

from echo_app import dictionary, speaker_groups
from echo_app.library import TRANSCRIPT
from test_speakers import _voice
from test_ui import _transcribed, lib, pump, qapp, window  # noqa: F401 - fixtures


_draws = iter(range(1000, 100000))


def _near(seed: int, amount: float) -> list[float]:
    """Voice `seed` heard another way (the other track, another microphone): a fresh unit of noise
    times `amount` on it, so its similarity to the voice is 1 / sqrt(1 + amount²)."""
    base = _voice(seed)
    noise = np.random.default_rng(next(_draws)).normal(size=256)
    noise -= (noise @ base) * base  # across the voice, so the similarity is exact
    v = base + amount * noise / np.linalg.norm(noise)
    return list(v / np.linalg.norm(v))


def _call(lib, tmp_path, speakers: list[tuple[int, list[float], float]]):
    """A call already labeled: each speaker as (track, centroid, seconds of speech)."""
    rec = _transcribed(lib, tmp_path)
    segs, t = [], 0.0
    for n, (_track, _c, secs) in enumerate(speakers, 1):
        segs.append({"start": t, "end": t + secs, "text": f"Habla {n}.", "paragraph": True, "speaker": n})
        t += secs + 1
    info = {"count": len(speakers), "centroids": {str(n): c for n, (_t, c, _s) in enumerate(speakers, 1)},
            "tracks": {str(n): tr for n, (tr, _c, _s) in enumerate(speakers, 1)}, "suggested": {}}
    rec.path(TRANSCRIPT).write_text(json.dumps({"text": "x", "segments": segs, "speakers": info,
                                                "created": "2026-11-03T10:00:00-03:00"}))
    return rec


def test_one_voice_on_both_tracks_is_one_speaker(lib, tmp_path):
    # Three people; each one's voice reached both tracks (no headphones), plus a fragment.
    rec = _call(lib, tmp_path, [(0, _near(1, 0.0), 600), (0, _near(2, 0.6), 20), (1, _near(2, 0.0), 900),
                                (1, _near(1, 0.6), 90), (1, _near(3, 0.0), 300), (0, _near(4, 0.0), 5)])
    sims = {(a, b): speaker_groups.similarity(_near(a, 0.0), _near(b, 0.6)) for a, b in ((1, 1), (2, 2), (1, 2))}
    assert sims[(1, 1)] > speaker_groups.CROSS_TRACK > sims[(1, 2)]
    joined, named = speaker_groups.apply(rec, voices={})
    rec = rec.reload()
    assert joined == 3 and named == []
    # Each twin joins the speaker with more speech; the 5 s fragment joins the nearest voice.
    assert rec.meta.speaker_merges == {"2": 3, "4": 1, "6": rec.speaker(6)} and rec.speaker(6) in (1, 3, 5)
    assert rec.speaker_numbers() == [1, 3, 5] and rec.meta.speakers_grouped == speaker_groups.VERSION


def test_never_joins_people_the_user_told_apart(lib, tmp_path):
    rec = _call(lib, tmp_path, [(0, _near(1, 0.0), 600), (1, _near(1, 0.3), 600)])
    rec.update(speakers={"1": "Ana", "2": "Bruno"})
    assert speaker_groups.apply(rec, voices={}) == (0, [])
    assert rec.reload().meta.speaker_merges == {}
    # The same name twice is one person, whatever the tracks.
    rec = _call(lib, tmp_path, [(0, _near(1, 0.0), 600), (0, _near(5, 0.0), 600)])
    rec.update(speakers={"1": "Ana", "2": "Ana"})
    speaker_groups.apply(rec, voices={})
    assert rec.reload().speaker(2) == 1


def test_known_voices_suggest_join_and_name(lib, tmp_path):
    voices = {"Lucía": {"voice": _near(1, 0.0), "recordings": 3},
              "Pablo": {"voice": _near(2, 0.0), "recordings": 1},
              "Tomás": {"voice": _near(3, 0.0), "recordings": 4}}
    # Lucía twice on one track (two microphones), Pablo clearly, and someone half like Tomás.
    # Lucía through two microphones: 0.8 like her voice, 0.64 like each other (noise across both).
    base, rng = _voice(1), np.random.default_rng(5)
    n1, n2 = rng.normal(size=256), rng.normal(size=256)
    n1 -= (n1 @ base) * base
    n1 /= np.linalg.norm(n1)
    n2 -= (n2 @ base) * base + (n2 @ n1) * n1
    n2 /= np.linalg.norm(n2)
    lucia = [list((base + 0.75 * n) / np.linalg.norm(base + 0.75 * n)) for n in (n1, n2)]
    rec = _call(lib, tmp_path, [(0, lucia[0], 300), (0, lucia[1], 200), (0, _near(2, 0.2), 300),
                                (0, _near(3, 3.0), 300)])
    assert speaker_groups.similarity(*lucia) < 1 - 0.35  # too far apart for the labeling to make one
    joined, named = speaker_groups.apply(rec, voices=voices)
    rec = rec.reload()
    assert rec.speaker(2) == 1 and joined == 1  # both sound like Lucía
    # Lucía is certain and learned from 3 recordings: named. Pablo's voice is from one recording:
    # suggested, not named. The fourth is not close enough to anyone to suggest.
    assert rec.meta.speakers == {"1": "Lucía"} and named == ["Lucía"] and rec.meta.speakers_by_voice == [1]
    assert speaker_groups.suggestions(rec, voices) == {3: "Pablo"}
    assert speaker_groups.ranked(rec, 4, voices)[0] == "Tomás"
    # A voice learned only from this recording does not recognize it.
    assert speaker_groups.known_match(_near(1, 0.0), {"Lucía": {"voice": _near(1, 0.0), "recordings": 1,
                                                                "parts": {rec.id: _near(1, 0.0)}}},
                                      exclude=rec.id)[0] is None


def test_the_window_groups_older_recordings_once_and_offers_known_people(window, lib, tmp_path, monkeypatch):
    monkeypatch.setattr(dictionary, "voices", lambda: {"Lucía": {"voice": _near(1, 0.0), "recordings": 1}})
    rec = _call(lib, tmp_path, [(0, _near(1, 0.4), 600), (1, _near(1, 0.3), 300), (1, _near(6, 0.0), 300)])
    messages = []
    window.transcript.message.connect(messages.append)
    window._select(rec.id)
    pump(200)
    rec = rec.reload()
    assert rec.speaker(2) == 1 and rec.meta.speakers_grouped == speaker_groups.VERSION
    assert any("joined 1 speaker" in m for m in messages)
    tp = window.transcript
    # Lucía's voice is from one recording: suggested on the bar, with the others in the dropdown.
    assert tp._ask == 1 and "sounds like <b>Lucía</b>" in tp.name_text.text()
    tp._name_someone_else()
    assert tp.name_pick.isVisibleTo(tp)
    dictionary.update(lambda d: d.add(dictionary.PEOPLE, "Tomás"))
    menu = tp._name_menu()
    assert [a.text() for a in menu.actions()] == ["Sounds closest to", "Lucía", "Everyone", "Tomás"]
    next(a for a in menu.actions() if a.text() == "Tomás").trigger()  # choosing one names the speaker
    assert rec.reload().meta.speakers.get("1") == "Tomás"
    tp.name_speaker(1, "")
    # Naming a speaker after someone already named here makes them one.
    tp.name_speaker(1, "Lucía")
    tp.name_speaker(3, "Lucía")
    assert rec.reload().speaker(3) == 1


def test_group_again_with_voices_learned_since(window, lib, tmp_path, monkeypatch):
    rec = _call(lib, tmp_path, [(0, _near(1, 0.75), 600), (0, _near(1, 0.75), 400), (1, _near(6, 0.0), 300)])
    known: dict = {}
    monkeypatch.setattr(dictionary, "voices", lambda: known)
    messages = []
    window.transcript.message.connect(messages.append)
    window._select(rec.id)
    pump(200)
    assert rec.reload().speaker_numbers() == [1, 2, 3]  # grouped once: nothing known, nothing to join
    known["Lucía"] = {"voice": _near(1, 0.0), "recordings": 2}  # learned since, in other recordings
    window.transcript.group_again()
    rec = rec.reload()
    assert rec.speaker(2) == 1 and rec.meta.speakers.get("1") == "Lucía"
    assert messages[-1] == "Speakers: joined 1 speaker and named Lucía by voice."
    window.transcript.group_again()
    assert messages[-1] == "Speakers: nothing to join; each one sounds like someone else."

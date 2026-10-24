from echo_app.worker import planning
from echo_app.worker.planning import MAX_PASSAGE, plan


def test_short_regions_merge_into_one_passage():
    ps = plan([(0.5, 3.0), (3.4, 6.0), (6.3, 9.0)])
    assert [(p.start, p.end) for p in ps] == [(0.5, 9.0)]
    assert ps[0].paragraph


def test_cut_at_widest_pause_within_limit():
    # 10 s regions separated by pauses; the widest pause (2.5 s) inside the window wins.
    regions = [(0, 9), (9.3, 14), (16.5, 24), (24.2, 40)]
    ps = plan(regions)
    assert ps[0].end == 14 and ps[1].start == 16.5
    assert all(p.duration <= MAX_PASSAGE for p in ps)
    assert ps[1].paragraph  # 2.5 s pause starts a paragraph


def test_prefers_passages_of_at_least_eight_seconds():
    # A wide pause right after 2 s should not create a tiny passage.
    regions = [(0, 2), (4, 12), (12.5, 20), (20.4, 30)]
    ps = plan(regions)
    assert ps[0].duration >= 8


def test_long_region_split_at_quietest_point():
    calls = []

    def quietest(lo, hi):
        calls.append((lo, hi))
        return lo + 1.0

    ps = plan([(0, 70)], quietest)
    assert all(p.duration <= MAX_PASSAGE for p in ps)
    assert ps[0].end == 24.0 and calls[0] == (23.0, 28.0)
    assert ps[-1].end == 70


def test_every_region_covered_once_and_in_order():
    import random

    rnd = random.Random(1)
    t, regions = 0.0, []
    for _ in range(500):
        t += rnd.uniform(0.1, 4)
        d = rnd.uniform(0.3, 40)
        regions.append((t, t + d))
        t += d
    ps = plan(regions, lambda lo, hi: (lo + hi) / 2)
    assert all(p.duration <= MAX_PASSAGE + 1e-9 for p in ps)
    assert ps[0].start == regions[0][0] and ps[-1].end == regions[-1][1]
    assert all(a.end <= b.start for a, b in zip(ps, ps[1:]))
    covered = sum(p.duration for p in ps)
    speech = sum(e - s for s, e in regions)
    assert covered >= speech  # gaps inside passages are included, nothing dropped


def test_join_text_paragraphs():
    segs = [{"text": " Hola.", "paragraph": True}, {"text": "Qué tal.", "paragraph": False},
            {"text": "", "paragraph": True}, {"text": "Otro tema.", "paragraph": True}]
    assert planning.join_text(segs) == "Hola. Qué tal.\n\nOtro tema."


def test_empty():
    assert plan([]) == []


def test_long_paragraphs_are_broken():
    # Continuous reading: 1 s pauses every 10 s for 10 minutes, never a 2 s pause.
    regions = [(i * 11.0, i * 11.0 + 10.0) for i in range(55)]
    ps = plan(regions)
    starts = [p for p in ps if p.paragraph]
    assert len(starts) >= 5
    length, longest = 0.0, 0.0
    for p in ps:
        if p.paragraph:
            length = 0.0
        length += p.duration
        longest = max(longest, length)
    assert longest <= planning.PARAGRAPH_HARD_LIMIT + planning.MAX_PASSAGE

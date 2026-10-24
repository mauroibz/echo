"""Linked sets: the files, membership rules and the timeline."""

import json
import os
import time

import pytest

from echo_app import sets
from echo_app.library import Library


def _rec(library, title, created, duration=120.0, text=None):
    rec = library.create(title, "imported", duration=duration)
    rec.update(created=created)
    if text:
        rec.save_edited(text)
    return rec


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path / "data")


def _three(lib):
    return (_rec(lib, "Nota 2", "2026-10-23T14:04:00-03:00"),
            _rec(lib, "Nota 1", "2026-10-23T14:02:00-03:00"),
            _rec(lib, "Nota 3", "2026-10-23T14:06:00-03:00"))


def test_link_orders_by_date_and_writes_one_file(lib):
    b, a, c = _three(lib)
    s = sets.link(lib, [b.id, c.id, a.id])
    assert s.members == [a.id, b.id, c.id] and s.title == "Nota 1 (+2)" and s.title_auto
    files = list((lib.data_dir / "sets").glob("*.json"))
    assert [f.stem for f in files] == [s.id]
    assert json.loads(files[0].read_text())["members"] == [a.id, b.id, c.id]
    # The members' folders are untouched.
    assert "set" not in json.loads((a.folder / "meta.json").read_text())


def test_link_needs_two(lib):
    a = _rec(lib, "Sola", "2026-10-23T14:02:00-03:00")
    with pytest.raises(ValueError):
        sets.link(lib, [a.id])


def test_adding_to_a_set_and_merging_sets(lib):
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id])
    s2 = sets.link(lib, [c.id, s.id])
    assert s2.id == s.id and s2.members == [a.id, b.id, c.id]
    d, e = _rec(lib, "D", "2026-10-24T10:00:00-03:00"), _rec(lib, "E", "2026-10-24T10:01:00-03:00")
    other = sets.link(lib, [d.id, e.id])
    merged = sets.link(lib, [s.id, other.id])
    assert merged.members == [a.id, b.id, c.id, d.id, e.id]
    assert [x.id for x in sets.load_all(lib)] == [s.id]


def test_one_set_per_recording(lib):
    b, a, c = _three(lib)
    s1 = sets.link(lib, [a.id, b.id, c.id])
    d = _rec(lib, "D", "2026-10-24T10:00:00-03:00")
    s2 = sets.link(lib, [c.id, d.id])
    assert sets.get(lib, s1.id).members == [a.id, b.id]
    assert sets.get(lib, s2.id).members == [c.id, d.id]
    # Taking one more out leaves one member: the first set is dissolved.
    sets.link(lib, [s2.id, b.id])
    assert sets.get(lib, s1.id) is None and sets.set_of(lib, a.id) is None


def test_missing_member_is_skipped_and_comes_back(lib, tmp_path):
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id, c.id])
    away = tmp_path / "trash"
    away.mkdir()
    os.rename(b.folder, away / b.id)
    assert [r.id for r in sets.present(lib, sets.get(lib, s.id))] == [a.id, c.id]
    assert sets.get(lib, s.id).members == [a.id, b.id, c.id]  # the file is not rewritten
    os.rename(away / b.id, b.folder)
    assert [r.id for r in sets.present(lib, sets.get(lib, s.id))] == [a.id, b.id, c.id]


def test_conflicting_claims_newest_file_wins(lib):
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id])
    # A second file claiming b, written later (as a sync tool would bring it).
    other = {"id": "set_other", "title": "Otro", "members": [b.id, c.id], "created": ""}
    path = lib.data_dir / "sets" / "set_other.json"
    path.write_text(json.dumps(other))
    later = time.time() + 5
    os.utime(path, (later, later))
    loaded = {x.id: x for x in sets.load_all(lib)}
    assert loaded["set_other"].members == [b.id, c.id] and loaded[s.id].members == [a.id]
    assert sets.membership(sets.load_all(lib))[b.id] == "set_other"


def test_move_reorders_and_unlink_dissolves(lib):
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id, c.id])
    assert sets.move(lib, s.id, c.id, 0).members == [c.id, a.id, b.id]
    sets.unlink(lib, a.id)
    assert sets.get(lib, s.id).members == [c.id, b.id]
    sets.unlink(lib, b.id)
    assert sets.get(lib, s.id) is None


def test_titles(lib):
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id])
    a.save_edited("Te cuento lo del viaje. Fue largo.")
    sets.refresh_title(lib, sets.get(lib, s.id))
    assert sets.get(lib, s.id).title == "Te cuento lo del viaje (+1)"
    sets.rename(lib, s.id, "Audios de Lucía")
    a.save_edited("Otra cosa.")
    sets.refresh_title(lib, sets.get(lib, s.id))
    assert sets.get(lib, s.id).title == "Audios de Lucía" and not sets.get(lib, s.id).title_auto
    s2 = sets.link(lib, [c.id, s.id], title="Viaje")
    assert s2.title == "Viaje"


def test_cleanup_removes_sets_with_no_members(lib, tmp_path):
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id])
    keep = sets.link(lib, [c.id, _rec(lib, "D", "2026-10-24T10:00:00-03:00").id])
    for r in (a, b):
        os.rename(r.folder, tmp_path / r.id)
    assert sets.cleanup(lib) == 1
    assert sets.get(lib, s.id) is None and sets.get(lib, keep.id) is not None


def test_timeline_uses_cropped_spans(lib):
    a = _rec(lib, "A", "2026-10-23T14:02:00-03:00", duration=100.0)
    b = _rec(lib, "B", "2026-10-23T14:04:00-03:00", duration=60.0)
    b.update(crop_start=10.0, crop_end=40.0)
    tl = sets.timeline([a, b])
    assert [(p.offset, p.start, p.length) for p in tl] == [(0.0, 0.0, 100.0), (100.0, 10.0, 30.0)]
    assert sets.total(tl) == 130.0 and sets.part_at(tl, 99.9) == 0 and sets.part_at(tl, 100.0) == 1
    assert tl[1].to_set(15.0) == 105.0 and tl[1].to_part(105.0) == 15.0
    assert sets.part_at(tl, 500) == 1


def test_index_lists_sets_and_migrates_from_schema_2(lib):
    import sqlite3

    from echo_app.index import Index

    db = sqlite3.connect(lib.data_dir / "library.sqlite")
    db.execute("CREATE TABLE recordings (id TEXT)")
    db.execute("PRAGMA user_version=2")
    db.commit()
    db.close()
    b, a, c = _three(lib)
    s = sets.link(lib, [a.id, b.id])
    idx = Index(lib)
    idx.sync()
    assert idx.sets() == [{"id": s.id, "title": s.title, "members": [a.id, b.id], "newest": b.meta.created}]
    # A set whose second member is gone is not listed as a set.
    import shutil

    shutil.rmtree(b.folder)
    idx.sync()
    assert idx.sets() == []
    idx.close()


def test_worker_titles_a_set_from_its_first_part(tmp_path):
    from echo_app import importer
    from test_quick_note import _transcribe
    from test_ui import wav

    lib_ = Library(tmp_path / "data")
    a = importer.import_file(lib_, wav(tmp_path / "a.wav", 1)).recording
    b = importer.import_file(lib_, wav(tmp_path / "b.wav", 1, 300)).recording
    a.update(created="2026-10-23T14:02:00-03:00")
    b.update(created="2026-10-23T14:04:00-03:00")
    s = sets.link(lib_, [a.id, b.id])
    assert s.title == "a (+1)"
    _transcribe(a, "Te cuento lo del viaje. Fue largo.")
    assert sets.get(lib_, s.id).title == "Te cuento lo del viaje (+1)"


SEGS_A = [{"start": 0.0, "end": 4.0, "text": "Hola, te cuento.", "paragraph": True},
          {"start": 5.0, "end": 9.0, "text": "Fue un viaje largo.", "paragraph": False}]
SEGS_B = [{"start": 12.0, "end": 16.0, "text": "Y al final llegamos.", "paragraph": True}]


def _transcribed_pair(lib):
    from echo_app.fsutil import atomic_write_json
    from echo_app.worker.planning import join_text

    a = _rec(lib, "Nota 1", "2026-10-23T14:02:00-03:00", duration=10.0)
    b = _rec(lib, "Nota 2", "2026-10-23T14:04:00-03:00", duration=20.0)
    b.update(crop_start=10.0)
    for rec, segs in ((a, SEGS_A), (b, SEGS_B)):
        atomic_write_json(rec.path("transcript.json"), {"segments": segs, "text": join_text(segs), "language": "es"})
    return a, b


def test_set_export_formats(lib):
    from echo_app import export

    a, b = _transcribed_pair(lib)
    txt = export.render_set("Viaje", [a, b], ".txt")
    assert txt == ("Nota 1 · 2026-10-23 14:02 · 0:10\n\nHola, te cuento. Fue un viaje largo.\n\n"
                   "Nota 2 · 2026-10-23 14:04 · 0:10\n\nY al final llegamos.\n")
    md = export.render_set("Viaje", [a, b], ".md")
    assert md.startswith("# Viaje\n\n_2026-10-23 14:02 – 2026-10-23 14:04_\n\n## Nota 1\n\n_2026-10-23 14:02 · 0:10_")
    # Part 2 starts at 10 s on the set timeline; its passage at 12 s of its audio (crop 10) is at 12 s.
    srt = export.render_set("Viaje", [a, b], ".srt")
    assert "3\n00:00:12,000 --> 00:00:16,000\nY al final llegamos." in srt
    data = json.loads(export.render_set("Viaje", [a, b], ".json", "set_x"))
    assert data["parts"][1]["offset"] == 10.0 and data["segments"][2] == {
        "start": 12.0, "end": 16.0, "text": "Y al final llegamos.", "paragraph": True, "part": 1}
    stamped = export.set_with_timestamps([a, b])
    assert stamped == ("Nota 1 · 2026-10-23 14:02 · 0:10\n\n[0:00] Hola, te cuento.\n[0:05] Fue un viaje largo.\n\n"
                       "Nota 2 · 2026-10-23 14:04 · 0:10\n\n[0:12] Y al final llegamos.\n")


def test_cli_link_list_export_unlink(lib, capsys):
    from echo_app import cli, settings

    settings.save(settings.Settings(data_dir=str(lib.data_dir)))
    a, b = _transcribed_pair(lib)
    lone = _rec(lib, "Suelta", "2026-10-22T09:00:00-03:00")
    assert cli.main(["link", b.id, a.id, "--title", "Viaje"]) == 0
    sid = capsys.readouterr().out.split()[0]
    assert sets.get(lib, sid).members == [a.id, b.id]
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(sid) and "2 parts  Viaje" in out[0]
    assert out[1].startswith(f"  {a.id}") and out[2].startswith(f"  {b.id}") and out[3].startswith(lone.id)
    assert cli.main(["list", "llegamos"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and out[1].startswith(f"  {b.id}")
    assert cli.main(["export", sid, "--format", "srt"]) == 0
    assert "00:00:12,000" in capsys.readouterr().out
    assert cli.main(["link", lone.id]) == 2
    assert cli.main(["unlink", a.id]) == 0
    assert sets.get(lib, sid) is None
    assert cli.main(["unlink", a.id]) == 1
    capsys.readouterr()


class _FakeInner:
    """A Playback stand-in: records what was played; `finish()` ends the current pipeline."""

    def __init__(self):
        self.path, self.speed, self.error = None, 1.0, None
        self.calls, self._pos, self._end, self.playing, self._ended = [], 0.0, None, False, False

    def load(self, path, duration):
        self.path, self.playing, self._pos = path, False, 0.0

    def seek(self, sec):
        self._pos = sec

    def play(self, start=None, end=None):
        self._pos = self._pos if start is None else start
        self._end, self.playing = end, True
        self.calls.append((self.path.parent.name if self.path else None, round(self._pos, 2), end and round(end, 2)))

    def position(self):
        return self._pos

    def finish(self):
        self._pos, self._ended = self._end, True

    def poll(self):
        if self.playing and self._ended:
            self.playing, self._ended = False, False
            return True
        return False

    def pause(self):
        self.playing = False

    stop = pause

    def set_speed(self, s):
        self.speed = s


def test_set_playback_hands_over_to_the_next_part(lib):
    from echo_app.audio.playback import SetPlayback

    a = _rec(lib, "A", "2026-10-23T14:02:00-03:00", duration=10.0)
    b = _rec(lib, "B", "2026-10-23T14:04:00-03:00", duration=20.0)
    b.update(crop_start=5.0, crop_end=15.0)
    for r in (a, b):
        (r.folder / "audio.wav").write_bytes(b"x")
        r.update(audio="audio.wav")
    pb = SetPlayback()
    pb.inner = _FakeInner()
    pb.load(sets.timeline([lib.get(a.id), lib.get(b.id)]))
    assert pb.duration == 20.0
    pb.play(0.0)
    assert pb.inner.calls == [(a.id, 0.0, 10.0)]
    pb.inner.finish()
    assert pb.poll() is False and pb.inner.calls[-1] == (b.id, 5.0, 15.0)  # the next part, from its crop
    assert pb.position() == 10.0
    pb.inner.finish()
    assert pb.poll() is True and pb.position() == 20.0
    # Seeking into the second part while stopped, then a span inside it.
    pb.seek(12.5)
    assert pb.k == 1 and pb.inner.position() == 7.5
    pb.play(11.0, 13.0)
    assert pb.inner.calls[-1] == (b.id, 6.0, 8.0)
    pb.inner.finish()
    assert pb.poll() is True
    # Playing from the end starts over.
    pb.seek(20.0)
    pb.play()
    assert pb.inner.calls[-1] == (a.id, 0.0, 10.0)


def _import(lib_, tmp_path, name, seconds=1.0):
    from echo_app import importer
    from test_ui import wav

    return importer.import_file(lib_, wav(tmp_path / name, seconds, 200 + len(name) * 7 + int(seconds * 13))).recording


def test_bursts_of_android_notes(tmp_path):
    lib_ = Library(tmp_path / "data")
    a = _import(lib_, tmp_path, "PTT-20261023-WA0004.opus")
    b = _import(lib_, tmp_path, "PTT-20261023-WA0005.opus")
    c = _import(lib_, tmp_path, "PTT-20261023-WA0008.opus")  # two numbers skipped: a photo, a file
    far = _import(lib_, tmp_path, "PTT-20261023-WA0020.opus")
    other_day = _import(lib_, tmp_path, "PTT-20261024-WA0009.opus")
    offers = sets.bursts(lib_, [a.id, b.id, c.id, far.id, other_day.id])
    assert [o.ids for o in offers] == [[a.id, b.id, c.id]] and offers[0].set_id is None
    # Linked, and a later note arrives from a watched folder: offered as an addition.
    st = sets.link(lib_, offers[0].ids)
    d = _import(lib_, tmp_path, "PTT-20261023-WA0009.opus")
    offers = sets.bursts(lib_, [d.id])
    assert [(o.ids, o.set_id, o.set_title) for o in offers] == [([d.id], st.id, st.title)]
    # Nothing new in a run: no offer.
    assert sets.bursts(lib_, [far.id]) == []


def test_bursts_of_desktop_notes_by_time(tmp_path):
    lib_ = Library(tmp_path / "data")
    a = _import(lib_, tmp_path, "WhatsApp Ptt 2026-10-23 at 14.02.11.ogg", 120)
    b = _import(lib_, tmp_path, "WhatsApp Ptt 2026-10-23 at 14.04.30.ogg", 60)
    c = _import(lib_, tmp_path, "WhatsApp Ptt 2026-10-23 at 14.30.00.ogg", 30)  # 25 minutes later
    plain = _import(lib_, tmp_path, "entrevista.wav")
    plain.update(created="2026-10-23T14:05:00-03:00")
    offers = sets.bursts(lib_, [a.id, b.id, c.id, plain.id])
    assert [o.ids for o in offers] == [[a.id, b.id]]
    assert offers[0].key == ",".join(sorted([a.id, b.id]))


def test_android_notes_of_one_day_are_ordered_by_number(tmp_path):
    lib_ = Library(tmp_path / "data")
    c = _import(lib_, tmp_path, "PTT-20261023-WA0012.opus")
    a = _import(lib_, tmp_path, "PTT-20261023-WA0010.opus")
    b = _import(lib_, tmp_path, "PTT-20261023-WA0011.opus")
    for r in (a, b, c):
        r.update(created="2026-10-23T00:00:00-03:00")
    assert sets.link(lib_, [c.id, b.id, a.id]).members == [a.id, b.id, c.id]

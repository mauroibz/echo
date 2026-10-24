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

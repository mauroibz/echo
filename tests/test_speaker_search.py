"""Search by speaker: @name finds where someone speaks, @name words finds what they said."""

import json

from echo_app import cli, settings
from echo_app.index import Index, parse_people, parse_query
from echo_app.library import EDITED, TRANSCRIPT, Library


def _lib(tmp_path):
    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    return Library(tmp_path / "data")


def meeting(lib, title, lines, names):
    """A transcribed recording: lines are (speaker number, text), 2 s each; names number -> name."""
    rec = lib.create(title, "imported", state="ready")
    segs = [{"start": 2.0 * i, "end": 2.0 * i + 1.5, "text": text, "paragraph": True, "speaker": who}
            for i, (who, text) in enumerate(lines)]
    rec.path(TRANSCRIPT).write_text(json.dumps({
        "text": "\n\n".join(t for _w, t in lines), "segments": segs, "language": "es",
        "speakers": {"count": len({w for w, _t in lines}), "centroids": {}, "suggested": {}}}))
    rec.update(speakers={str(k): v for k, v in names.items()})
    return rec


def ids(idx, q):
    return sorted(r["id"] for r in idx.list(q))


def test_who_speaks_and_what_they_said(tmp_path):
    lib = _lib(tmp_path)
    a = meeting(lib, "Weekly", [(1, "El precio sube en enero."), (2, "Y el precio de febrero?")],
                {1: "Ana López", 2: "Pedro"})
    b = meeting(lib, "Globex", [(1, "Hablemos del precio."), (2, "Bien.")], {1: "Pedro", 2: "Ana López"})
    c = meeting(lib, "Unnamed", [(1, "precio"), (2, "nada")], {})
    idx = Index(lib)
    idx.sync()
    assert ids(idx, "@ana") == sorted([a.id, b.id]) and ids(idx, "@LOPEZ") == sorted([a.id, b.id])
    assert ids(idx, "@ana_lo") == sorted([a.id, b.id]) and ids(idx, "@lopez_ana") == []
    assert ids(idx, "@ana precio") == [a.id]  # in b only Pedro said it
    assert ids(idx, "@pedro precio") == sorted([a.id, b.id])
    assert ids(idx, "@ana @pedro") == sorted([a.id, b.id]) and ids(idx, "@nadie") == []
    assert ids(idx, "precio") == sorted([a.id, b.id, c.id])  # words alone still search everything
    m = idx.speech_matches("@ana precio")
    assert set(m) == {a.id, b.id} and m[a.id]["numbers"] == [1] and m[b.id]["numbers"] == [2]
    assert m[a.id]["snippet"].startswith("Ana López: El precio sube") and m[b.id]["snippet"] is None
    assert idx.speakers() == [("Ana López", 2), ("Pedro", 2)]
    idx.close()


def test_passages_for_extensions(tmp_path):
    lib = _lib(tmp_path)
    lines = [(1, "Arrancamos."), (1, "El precio sube en enero."), (2, "Y el precio de febrero?")]
    a = meeting(lib, "Weekly", lines, {1: "Ana López", 2: "Pedro"})
    meeting(lib, "Otra", [(1, "Nada que ver.")], {})
    idx = Index(lib)
    idx.sync()
    got = idx.passages("precio enero")
    assert len(got) == 1 and got[0]["id"] == a.id and got[0]["start"] == 2.0 and got[0]["speaker"] == "Ana López"
    assert got[0]["text"] == "Arrancamos. El precio sube en enero. Y el precio de febrero?"  # one either side
    assert got[0]["title"] == "Weekly" and got[0]["end"] == 5.5
    assert [p["speaker"] for p in idx.passages("@pedro precio", context=0)] == ["Pedro"]
    assert len(idx.passages("precio", limit=1)) == 1 and idx.passages("nadie dijo esto") == []
    idx.close()


def test_edited_text_renames_and_speakers_off(tmp_path):
    lib = _lib(tmp_path)
    a = meeting(lib, "Weekly", [(1, "El precio sube."), (2, "Otra cosa.")], {1: "Ana", 2: "Pedro"})
    a.path(EDITED).write_text("El costo sube.\n\nOtra cosa.")  # the user's words are what is searched
    idx = Index(lib)
    idx.sync()
    assert ids(idx, "@ana costo") == [a.id] and ids(idx, "@ana precio") == []
    a.update(speakers={"1": "Lucía", "2": "Pedro"})
    idx.sync()
    assert ids(idx, "@ana") == [] and ids(idx, "@lucia costo") == [a.id]
    a.update(speakers_off=True)
    idx.sync()
    assert ids(idx, "@lucia") == []
    idx.close()


def test_query_parsing():
    assert parse_query("@ana precio #client:acme") == (["precio"], ["client:acme"])
    assert parse_people("@ana precio @pedro_g @") == ["ana", "pedro_g"]


def test_cli_list_by_speaker(tmp_path, capsys):
    lib = _lib(tmp_path)
    a = meeting(lib, "Weekly", [(1, "El precio sube."), (2, "Bien.")], {1: "Ana", 2: "Pedro"})
    meeting(lib, "Globex", [(1, "El precio."), (2, "Bien.")], {1: "Pedro", 2: "Ana"})
    capsys.readouterr()
    assert cli.main(["list", "@ana precio", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    rows = out if isinstance(out, list) else out.get("recordings", out)
    assert [r["id"] for r in rows] == [a.id]

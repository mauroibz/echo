"""Tags and notes: storage, the index, search syntax and the command line."""

from echo_app import cli, settings
from echo_app.index import Index, parse_query
from echo_app.library import Library, clean_tag


def _lib(tmp_path):
    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    return Library(tmp_path / "data")


def test_tags_are_cleaned_and_compared_folded(tmp_path):
    rec = _lib(tmp_path).create("t", "imported")
    assert rec.set_tags(["Entrevista", "#entrevista", "trabajo, Surus", "", "x" * 40]) == \
        ["Entrevista", "trabajo Surus", "x" * 32]
    assert clean_tag("a\nb") == "a b" and clean_tag("##") == ""


def test_index_filters_by_tags_and_searches_notes(tmp_path):
    lib = _lib(tmp_path)
    a = lib.create("Charla con Ana", "imported")
    a.set_tags(["entrevista", "Trabajo"])
    a.update(notes="Hablamos del presupuesto")
    b = lib.create("Diario", "imported")
    b.set_tags(["diario"])
    idx = Index(lib)
    idx.sync()
    ids = lambda q="", tags=(): [r["id"] for r in idx.list(q, tags=tags)]  # noqa: E731
    assert ids("#entrevista") == [a.id] and ids("#ENTREVISTA") == [a.id]
    assert ids("#entrevista #diario") == []  # tags combine with AND
    assert ids("presupuesto") == [a.id]  # notes are searchable
    assert ids("presupuesto", tags=["trabajo"]) == [a.id]
    assert idx.tag_counts() == [("diario", 1), ("entrevista", 1), ("Trabajo", 1)]
    idx.close()


def test_tags_survive_a_rescan(tmp_path):
    lib = _lib(tmp_path)
    a = lib.create("x", "imported")
    a.set_tags(["entrevista"])
    a.update(notes="nota secreta")
    (lib.data_dir / "library.sqlite").unlink(missing_ok=True)
    idx = Index(lib)
    idx.rebuild()
    assert [r["id"] for r in idx.list("#entrevista secreta")] == [a.id]


def test_parse_query():
    assert parse_query("hola #a mundo # #b") == (["hola", "mundo"], ["a", "b"])


def test_cli_tag_and_list(tmp_path, capsys):
    lib = _lib(tmp_path)
    a = lib.create("Charla", "imported")
    assert cli.main(["tag", a.id, "+entrevista", "+trabajo"]) == 0
    assert capsys.readouterr().out.strip() == "#entrevista #trabajo"
    assert cli.main(["tag", a.id, "-trabajo"]) == 0
    assert lib.get(a.id).meta.tags == ["entrevista"]
    capsys.readouterr()
    assert cli.main(["list", "--tag", "entrevista"]) == 0
    assert "Charla" in capsys.readouterr().out
    assert cli.main(["list", "--tag", "otro"]) == 0
    assert "No matches." in capsys.readouterr().out

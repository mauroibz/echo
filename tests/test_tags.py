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


def test_tag_categories_and_searching_a_whole_category(tmp_path):
    from echo_app.library import tag_category

    assert tag_category("client:Acme") == ("client", "Acme") and tag_category("client: Acme ") == ("client", "Acme")
    assert tag_category("nota") is None and tag_category("client:") is None and tag_category(":x") is None
    lib = _lib(tmp_path)
    a, b, c = (lib.create(t, "imported") for t in ("a", "b", "c"))
    a.set_tags(["client:Acme"])
    b.set_tags(["Client:Globex", "type:standup"])
    c.set_tags(["client", "nota"])  # a plain tag named like the category is not in it
    idx = Index(lib)
    idx.sync()
    ids = lambda q: sorted(r["id"] for r in idx.list(q))  # noqa: E731
    assert ids("#client:") == sorted([a.id, b.id]) and ids("#CLIENT:") == sorted([a.id, b.id])
    assert ids("#client:acme") == [a.id]
    assert ids("#client: #type:") == [b.id]
    idx.close()
    assert cli.main(["list", "--tag", "client:"]) == 0


def test_markdown_tags_nest_categories(tmp_path):
    from echo_app import export

    assert export._md_tag("client:Acme") == "#client/Acme" and export._md_tag("una nota") == "#una-nota"

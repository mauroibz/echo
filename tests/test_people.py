"""People: profile files, everyone Echo knows, their recordings, and their tags in search."""

import json

from echo_app import cli, dictionary, people, settings
from echo_app.index import Index
from echo_app.library import Library
from test_speaker_search import meeting


def _lib(tmp_path):
    settings.save(settings.Settings(data_dir=str(tmp_path / "data")))
    return Library(tmp_path / "data")


def test_profiles_are_files_and_empty_ones_are_not(tmp_path):
    lib = _lib(tmp_path)
    assert people.load(lib, "Ana López") == people.Profile("Ana López")
    assert not people.folder(lib).exists()  # reading writes nothing
    people.save(lib, people.Profile("Ana López", "CFO de Acme", ["client:Acme", "client:Acme", "#vip"]))
    f = people.folder(lib) / "ana-lopez.json"
    assert json.loads(f.read_text()) == {"name": "Ana López", "notes": "CFO de Acme", "tags": ["client:Acme", "vip"],
                                         "email": ""}
    assert people.load(lib, "ana lópez").notes == "CFO de Acme"  # names compare folded
    people.save(lib, people.Profile("ana-lopez", "otra persona"))  # same slug, another name
    assert (people.folder(lib) / "ana-lopez-2.json").exists() and people.load(lib, "Ana López").notes == "CFO de Acme"
    people.save(lib, people.Profile("Ana López"))
    assert not f.exists()


def test_an_email_finds_the_person(tmp_path):
    lib = _lib(tmp_path)
    assert people.clean_email("Ana López <Ana@Acme.Example>") == "ana@acme.example"
    assert people.clean_email("no es un correo") == ""
    people.save(lib, people.Profile("Ana López", email=" ANA@acme.example "))
    assert people.load(lib, "Ana López").email == "ana@acme.example"
    assert people.by_email(lib, "mailto:ana@ACME.example").name == "Ana López"
    assert people.by_email(lib, "otro@acme.example") is None and people.by_email(lib, "") is None
    people.save(lib, people.Profile("Pedro", email="pedro@acme.example"))  # an email alone keeps the file
    assert people.by_email(lib, "pedro@acme.example").name == "Pedro"


def test_everyone_and_their_recordings(tmp_path):
    lib = _lib(tmp_path)
    a = meeting(lib, "Weekly", [(1, "Hola."), (2, "Chau."), (1, "Otra vez.")], {1: "Ana López", 2: "Pedro"})
    b = meeting(lib, "Globex", [(1, "Hola.")] * 2 + [(2, "x")], {1: "Pedro", 2: "Ana López"})
    a.update(created="2026-10-01T10:00:00-03:00")
    b.update(created="2026-10-20T10:00:00-03:00")
    dictionary.update(lambda d: d.add(dictionary.PEOPLE, "Lucía"))
    dictionary.remember_voice("Pedro", [1.0, 0.0])
    people.save(lib, people.Profile("Marta", "nunca habló"))
    idx = Index(lib)
    idx.sync()
    every = {p.name: p for p in people.everyone(lib, idx)}
    assert set(every) == {"Ana López", "Pedro", "Lucía", "Marta"}
    ana = every["Ana López"]
    assert ana.recordings == 2 and ana.seconds == 4.5 and ana.last.startswith("2026-10-20")
    assert every["Pedro"].has_voice and every["Lucía"].in_dictionary and every["Marta"].profile.notes == "nunca habló"
    recs = people.recordings_of(idx, "ana lopez")
    assert [r["id"] for r in recs] == [b.id, a.id] and recs[0]["number"] == 2 and recs[1]["seconds"] == 3.0
    idx.close()


def test_a_persons_tags_find_their_recordings(tmp_path):
    lib = _lib(tmp_path)
    a = meeting(lib, "Weekly", [(1, "Hola."), (2, "Chau.")], {1: "Ana", 2: "Pedro"})
    b = meeting(lib, "Globex", [(1, "Hola."), (2, "Chau.")], {1: "Pedro", 2: "Luis"})
    c = lib.create("Tagged", "imported")
    c.set_tags(["client:Acme"])
    people.save(lib, people.Profile("Ana", tags=["client:Acme"]))
    idx = Index(lib)
    idx.sync()
    ids = lambda q: sorted(r["id"] for r in idx.list(q))  # noqa: E731
    assert ids("#client:acme") == sorted([a.id, c.id]) and ids("#client:") == sorted([a.id, c.id])
    assert b.id not in ids("#client:")
    idx.close()


def test_forget_voice(tmp_path):
    dictionary.remember_voice("Pedro", [1.0, 0.0])
    dictionary.forget_voice("Pedro")
    assert "Pedro" not in dictionary.voices()


def test_cli_people(tmp_path, capsys):
    lib = _lib(tmp_path)
    a = meeting(lib, "Weekly", [(1, "Hola."), (2, "Chau.")], {1: "Ana", 2: "Pedro"})
    people.save(lib, people.Profile("Ana", "CFO", ["client:Acme"]))
    dictionary.update(lambda d: d.add(dictionary.PEOPLE, "Ana", ["Anita"]))
    capsys.readouterr()
    assert cli.main(["people", "--json"]) == 0
    out = {p["name"]: p for p in json.loads(capsys.readouterr().out)["people"]}
    assert out["Ana"] == {"name": "Ana", "email": None, "aliases": ["Anita"], "tags": ["client:Acme"], "notes": "CFO",
                          "voice": False, "recordings": [{"id": a.id, "title": "Weekly", "seconds": 1.5}]}
    assert cli.main(["people"]) == 0
    text = capsys.readouterr().out
    assert "Ana" in text and "CFO" in text and "Pedro" in text

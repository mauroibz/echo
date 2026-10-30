"""Extensions: loading, each hook, containment of failures, and the core's isolation."""

import ast
import json
import logging
import sys
from pathlib import Path

import pytest

from echo_app import cli, doctor, export, extensions
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures
from test_vault import _rec

SRC = Path(__file__).resolve().parent.parent / "src" / "echo_app"

FAKE = '''
from echo_app import doctor

seen = []


def register_cli(sub):
    p = sub.add_parser("hello", help="say hello")
    p.set_defaults(func=lambda args: print("hello from fake") or 0)


def doctor_checks():
    return [doctor.Check("Fake server", doctor.OK, "answers")]


def markdown_sections(rec):
    return [("Resumen", "# Tema\\n- un punto")]
'''


@pytest.fixture
def fake_ext(tmp_path, monkeypatch):
    """Load an extension named fake_ext from a temporary folder."""
    def install(source=FAKE, name="fake_ext"):
        d = tmp_path / "ext"
        d.mkdir(exist_ok=True)
        (d / f"{name}.py").write_text(source)
        monkeypatch.syspath_prepend(str(d))
        monkeypatch.setattr(extensions, "KNOWN", (name,))
        monkeypatch.delenv("ECHO_NO_EXTENSIONS", raising=False)
        extensions.loaded.cache_clear()
        return extensions.loaded()

    yield install
    extensions.loaded.cache_clear()
    sys.modules.pop("fake_ext", None)


def test_none_by_default():
    extensions.loaded.cache_clear()
    assert extensions.loaded() == ()
    assert extensions.gather("doctor_checks") == []


def test_switched_off_by_environment(fake_ext, monkeypatch):
    assert len(fake_ext()) == 1
    monkeypatch.setenv("ECHO_NO_EXTENSIONS", "1")
    extensions.loaded.cache_clear()
    assert extensions.loaded() == ()


def test_the_installers_choice(fake_ext, monkeypatch):
    monkeypatch.setenv("ECHO_EXTENSIONS", "")  # the launcher, installed without --with-studio
    assert fake_ext() == ()
    monkeypatch.setenv("ECHO_EXTENSIONS", "fake_ext\n")
    extensions.loaded.cache_clear()
    assert [m.__name__ for m in extensions.loaded()] == ["fake_ext"]
    monkeypatch.delenv("ECHO_EXTENSIONS")  # from a checkout: whatever is present
    extensions.loaded.cache_clear()
    assert extensions.chosen() == ("fake_ext",)


def test_doctor_names_the_extensions(fake_ext, monkeypatch):
    def line():
        return next(c for c in doctor.run_all(gpu=False) if c.name == "Extensions")

    extensions.loaded.cache_clear()
    assert line().detail == "none (Echo alone)" and "--with-studio" in line().fix
    fake_ext()
    assert line().status == doctor.OK and line().detail == "fake_ext"


def test_broken_extension_is_skipped(fake_ext, caplog):
    with caplog.at_level(logging.ERROR, logger="echo_app.extensions"):
        assert fake_ext("raise RuntimeError('broken on import')\n") == ()
    assert "broken on import" in caplog.text


def test_failing_hook_is_skipped(fake_ext, caplog):
    fake_ext("def doctor_checks():\n    raise ValueError('nope')\n")
    with caplog.at_level(logging.ERROR, logger="echo_app.extensions"):
        assert extensions.gather("doctor_checks") == []
    assert "nope" in caplog.text


def test_clashing_subcommand_leaves_the_cli_working(fake_ext, caplog):
    fake_ext("def register_cli(sub):\n    sub.add_parser('list')\n")
    with caplog.at_level(logging.ERROR, logger="echo_app.extensions"):
        names = cli._command_names(cli.build_parser())
    assert {"list", "transcribe"} <= names and "register_cli" in caplog.text


def test_cli_doctor_and_markdown_hooks(fake_ext, tmp_path, capsys):
    fake_ext()
    assert cli.main(["hello"]) == 0
    assert "hello from fake" in capsys.readouterr().out
    assert any(c.name == "Fake server" for c in doctor.run_all(gpu=False))
    from echo_app.library import Library

    note = export.to_markdown(_rec(Library(tmp_path / "data")))
    head, rest = note.split("## Resumen\n\n", 1)
    assert head.startswith("# Charla con Lucía") and rest.startswith("# Tema\n- un punto\n\nHola, soy Lucía.")


def test_window_without_extensions_has_no_switch(window):
    assert window.views.views() == []
    assert not window.views.bar.isVisible()
    assert window.views.stack.currentWidget() is window.transcript


def test_added_view_follows_the_selection(window, lib):
    from PySide6.QtWidgets import QLabel

    class View(QLabel):
        def __init__(self):
            super().__init__("summary")
            self.calls = []

        def show_subject(self, rec, linked):
            self.calls.append(rec.id if rec is not None else None)

    a = lib.create("Uno", "imported", duration=3.0)
    b = lib.create("Dos", "imported", duration=3.0)
    window.model.refresh()
    view = View()
    window.add_view("Summary", view)
    pump(50)
    assert window.views.bar.isVisible()
    assert [btn.text() for btn in window.views.buttons] == ["Transcript", "Summary"]
    window._select(a.id)
    window._select(b.id)
    assert view.calls[-2:] == [a.id, b.id]
    window.views.buttons[1].click()
    assert window.views.stack.currentWidget() is view
    # The shown recording's files changing reaches the view too.
    n = len(view.calls)
    b.update(notes="otra nota")
    assert wait_until(lambda: len(view.calls) > n)


def test_screen_and_show_recording(window, lib, monkeypatch):
    from PySide6.QtWidgets import QLabel

    a = lib.create("Uno", "imported", duration=30.0)
    b = lib.create("Dos", "imported", duration=30.0)
    window.model.refresh()
    window._select(a.id)
    screen = QLabel("Pendientes")
    btn = window.add_screen("Pending", "list-filter", screen, "Ctrl+Shift+T")
    assert window.screens.currentWidget() is window.content
    btn.click()
    assert window.screens.currentWidget() is screen and btn.isChecked()
    btn.click()
    assert window.screens.currentWidget() is window.content
    btn.click()
    played = []
    monkeypatch.setattr(window, "_seek_and_play", played.append)
    window.show_recording(b.id, at=12.5)  # a citation: back to the recording, playing from there
    assert window.screens.currentWidget() is window.content and not btn.isChecked()
    assert window.current().id == b.id and played == [12.5]
    btn.click()
    window.list.clicked.emit(window.model.index(window.model.row_of(a.id)))
    assert window.screens.currentWidget() is window.content


def test_person_sections(fake_ext, window, lib):
    from test_ui_people import _two_meetings

    fake_ext(FAKE + """
from PySide6.QtWidgets import QLabel

def person_sections(name):
    return [("Pendientes", QLabel("abiertas de " + name))]
""")
    _two_meetings(lib)
    window.model.refresh()
    window.open_people("Pedro")
    dlg = window._people_dialog
    texts = [dlg.sections.itemAt(i).widget().text() for i in range(dlg.sections.count())]
    assert texts == ["Pendientes", "abiertas de Pedro"]
    dlg.select("Ana López")
    pump(50)
    assert dlg.sections.itemAt(1).widget().text() == "abiertas de Ana López"
    dlg.close()


def test_transcribed_signal(window, lib):
    from echo_app.library import TRANSCRIPT

    old = lib.create("Ya transcrita", "imported", duration=3.0)
    old.path(TRANSCRIPT).write_text(json.dumps({"segments": [], "text": "hola"}))
    window.model.refresh()
    window._transcript_times[old.id] = window._transcript_time(old)
    got = []
    window.transcribed.connect(got.append)
    rec = lib.create("Nueva", "imported", duration=3.0)
    window.model.refresh()
    rec.path(TRANSCRIPT).write_text(json.dumps({"segments": [], "text": "buenas"}))
    rec.update(notes="")  # the folder changes as when the worker finishes
    assert wait_until(lambda: rec.id in got)
    assert old.id not in got


def test_settings_page_applies_and_can_refuse(qapp, lib):
    from PySide6.QtWidgets import QLineEdit

    from echo_app.ui.dialogs import SettingsDialog

    class Page(QLineEdit):
        applied = 0

        def apply(self):
            if not self.text():
                raise ValueError("write something")
            Page.applied += 1

    page = Page()
    d = SettingsDialog(recording_active=False, pages=[("Summaries", page)])
    assert d.tabs.tabText(d.tabs.count() - 1) == "Summaries"
    d.accept()
    assert d.result() == 0 and "Summaries: write something" in d.note.text()
    assert d.tabs.currentWidget() is page
    page.setText("ok")
    d.accept()
    assert Page.applied == 1 and d.result() == 1


NETWORK = {"socket", "ssl", "http", "urllib.request", "requests", "httpx", "aiohttp"}
DOWNLOAD = {"huggingface_hub"}  # the one-time model download, allowed in models.py only


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            if node.module.startswith("PySide6.QtNetwork"):
                names |= {f"QtNetwork.{a.name}" for a in node.names}
    return names


def test_core_never_imports_an_extension_or_the_network():
    problems = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for name in _imports(path):
            top = name.split(".")[0]
            if top in extensions.KNOWN:
                problems.append(f"{rel} imports the extension {name}")
            if name in NETWORK or top in {n for n in NETWORK if "." not in n}:
                problems.append(f"{rel} imports {name}")
            if top in DOWNLOAD and rel != "models.py":
                problems.append(f"{rel} imports {name} (only models.py downloads)")
            if name.startswith("QtNetwork.") and name not in ("QtNetwork.QLocalServer", "QtNetwork.QLocalSocket"):
                problems.append(f"{rel} imports {name}")
    assert problems == []

"""Bundles: chosen parts of recordings as Markdown, copied or zipped, in the window and the command line."""

import json
import zipfile

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from echo_app import bundle, cli, extensions, sets
from echo_app.library import Library
from test_extensions import fake_ext  # noqa: F401 - fixture
from test_speaker_search import meeting
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures
from test_vault import _rec

PARTS = '''
def bundle_parts(rec):
    if rec.meta.title == "Sin resumen":
        return []
    return [("summary", "Summary", "Resumen", "### Tema\\n- un punto"),
            ("actions", "Action items", "Acciones", "- [ ] **Enviar el presupuesto** (Ana)"),
            ("empty", "Empty", "Nada", "  ")]
'''


def test_echo_alone_bundles_the_transcript(tmp_path):
    library = Library(tmp_path / "data")
    rec = _rec(library)
    rec.update(notes="Primera charla.")
    assert bundle.available([rec]) == [("transcript", "Transcript")]
    assert bundle.render(rec) == ("# Charla con Lucía\n\n_2026-10-24 10:30_ · 1:12\n\n> Primera charla.\n\n"
                                  "## Transcripción\n\nHola, soy Lucía.\n\nHablemos del precio.\n\n"
                                  "Y ahora el cierre.\n")
    assert "[1:05] Y ahora el cierre." in bundle.render(rec, timestamps=True)
    empty = library.create("Vacía", "imported")
    assert bundle.available([empty]) == [] and bundle.render(empty) == ""
    assert bundle.text([empty, rec]) == bundle.render(rec)  # a recording with nothing is left out


def test_speakers_are_named(tmp_path):
    rec = meeting(Library(tmp_path / "data"), "Weekly", [(1, "El precio sube."), (2, "De acuerdo.")], {1: "Ana"})
    assert bundle.render(rec).endswith("## Transcripción\n\nAna: El precio sube.\n\nSpeaker 2: De acuerdo.\n")


def test_parts_from_an_extension_and_choosing_among_them(tmp_path, fake_ext):
    fake_ext(PARTS)
    library = Library(tmp_path / "data")
    rec, bare = _rec(library), _rec(library, "Sin resumen")
    assert bundle.available([bare, rec]) == [("transcript", "Transcript"), ("summary", "Summary"),
                                             ("actions", "Action items")]  # a blank part is not offered
    note = bundle.render(rec)
    assert note.index("## Resumen\n\n### Tema") < note.index("## Acciones\n\n- [ ] **Enviar") \
        < note.index("## Transcripción")  # the transcript, the longest, goes last
    only = bundle.render(rec, ["summary", "actions"])
    assert "## Resumen" in only and "Transcripción" not in only
    assert bundle.render(bare, ["summary"]) == ""
    assert [r.id for r, _md in bundle.notes([bare, rec], ["summary"])] == [rec.id]


def test_zip_has_a_note_per_recording(tmp_path):
    library = Library(tmp_path / "data")
    a, b, empty = _rec(library), _rec(library), library.create("Vacía", "imported")
    dest = tmp_path / "out.zip"
    assert bundle.write_zip([a, b, empty], dest) == 2
    with zipfile.ZipFile(dest) as z:
        names = z.namelist()
        assert names == ["2026-10-24 Charla con Lucía.md", f"2026-10-24 Charla con Lucía ({b.id}).md"]
        assert z.read(names[0]).decode() == bundle.render(a)
    before = dest.read_bytes()
    bundle.write_zip([a, b], dest)
    assert dest.read_bytes() == before  # the same bundle, the same file
    assert bundle.write_zip([empty], tmp_path / "none.zip") == 0 and not (tmp_path / "none.zip").exists()


def test_a_set_is_its_parts_in_order(tmp_path):
    library = Library(tmp_path / "data")
    a, b = _rec(library, "Uno"), _rec(library, "Dos")
    st = sets.link(library, [b.id, a.id])
    assert [r.id for r in bundle.expand(library, [st.id, a.id])] == [r.id for r in sets.present(library, st)]
    with pytest.raises(KeyError):
        bundle.expand(library, ["nope"])


def test_command_line(tmp_path, capsys, fake_ext):
    from echo_app import settings

    fake_ext(PARTS)
    cfg, _ = settings.load()
    library = Library(cfg.data_path)
    a, b = _rec(library, "Uno"), _rec(library, "Dos")
    assert cli.main(["bundle", a.id, b.id]) == 0
    out = capsys.readouterr().out
    assert out == bundle.text([a, b]) and out.count("## Resumen") == 2
    assert cli.main(["bundle", a.id, "--parts", "summary,actions"]) == 0
    assert "Transcripción" not in capsys.readouterr().out
    assert cli.main(["bundle", a.id, "--parts", "minutes"]) == 2
    assert "they have: transcript, summary, actions" in capsys.readouterr().err
    assert cli.main(["bundle", "nope"]) == 1 and "No recording or linked set nope" in capsys.readouterr().err
    dest = tmp_path / "b.zip"
    assert cli.main(["bundle", a.id, b.id, "--timestamps", "--out", str(dest)]) == 0
    with zipfile.ZipFile(dest) as z:
        assert len(z.namelist()) == 2 and "[0:00] Hola, soy Lucía." in z.read(z.namelist()[0]).decode()
    md = tmp_path / "b.md"
    assert cli.main(["bundle", a.id, "--out", str(md)]) == 0 and md.read_text() == bundle.render(a)
    empty = library.create("Sin resumen", "imported")
    assert cli.main(["bundle", empty.id]) == 1 and "Nothing to bundle" in capsys.readouterr().err


def _answer(monkeypatch, action=None, uncheck=(), times=None):
    """Answer the next Bundle dialog without showing it; returns what it offered."""
    from echo_app.ui.dialogs import BundleDialog

    seen = {}

    def run(dlg):
        seen["parts"] = {k: box.isChecked() for k, box in dlg.checks.items()}
        seen["times"] = dlg.times.isChecked()
        if action is None:
            return 0
        for k in uncheck:
            dlg.checks[k].setChecked(False)
        if times is not None:
            dlg.times.setChecked(times)
        dlg.action = action
        return 1

    monkeypatch.setattr(BundleDialog, "exec", run)
    return seen


def test_window_copies_the_selection_and_remembers_the_choices(window, lib, monkeypatch, fake_ext):
    fake_ext(PARTS)
    a, b = _rec(lib, "Uno"), _rec(lib, "Dos")
    b.update(created="2026-10-25T09:00:00-03:00")
    window.model.refresh()
    window._select(a.id)
    pump(50)
    assert window.a_bundle.isEnabled() and window.a_bundle.shortcut().toString() == "Ctrl+Shift+B"
    seen = _answer(monkeypatch, "copy", uncheck=["transcript"])
    window.bundle_selected()
    assert seen["parts"] == {"transcript": True, "summary": True, "actions": True} and not seen["times"]
    assert wait_until(lambda: "Copied 1 recording, about" in window.toast.text())
    assert QApplication.clipboard().text() == bundle.render(a, ["summary", "actions"])
    assert window.state.get("bundle_off") == ["transcript"]
    # Several selected: oldest first, with the choices of the last time.
    window.list.selectAll()
    pump(50)
    assert window.selection_bar.isVisible() and window.bar_bundle.isVisible()
    seen = _answer(monkeypatch, "copy")
    window.bar_bundle.click()
    assert seen["parts"] == {"transcript": False, "summary": True, "actions": True}
    assert wait_until(lambda: "Copied 2 recordings" in window.toast.text())
    text = QApplication.clipboard().text()
    assert text == bundle.text([a, b], ["summary", "actions"]) and text.index("# Uno") < text.index("# Dos")
    # Cancelled: nothing copied, nothing remembered.
    QApplication.clipboard().setText("antes")
    _answer(monkeypatch)
    window.bundle_selected()
    pump(200)
    assert QApplication.clipboard().text() == "antes"


def test_window_saves_a_zip(window, lib, monkeypatch, tmp_path):
    a = _rec(lib, "Uno")
    bare = lib.create("Vacía", "imported")
    window.model.refresh()
    window._select(bare.id)
    pump(50)
    _answer(monkeypatch, "zip")
    window.bundle_selected()
    assert "Nothing to bundle yet" in window.toast.text()  # no dialog for nothing
    window.list.selectAll()
    pump(50)
    dest = tmp_path / "bundle"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(dest), "Zip (*.zip)"))
    seen = _answer(monkeypatch, "zip", times=True)
    window.bundle_selected()
    assert list(seen["parts"]) == ["transcript"]  # Echo alone
    assert wait_until(lambda: "1 had none of those parts" in window.toast.text())
    with zipfile.ZipFile(tmp_path / "bundle.zip") as z:
        assert z.read("2026-10-24 Uno.md").decode() == bundle.render(a, timestamps=True)
    assert window.state.get("bundle_times") is True


def test_dialog_needs_a_part_and_copy_is_the_default(qapp):
    from echo_app.ui.dialogs import BundleDialog

    dlg = BundleDialog("3 recordings", [("transcript", "Transcript"), ("summary", "Summary")], off=["summary"])
    assert dlg.keys() == ["transcript"] and dlg.off() == ["summary"]
    assert dlg.copy_btn.isDefault() and dlg.copy_btn.isEnabled() and dlg.times.isEnabled()
    dlg.checks["transcript"].setChecked(False)
    assert not dlg.copy_btn.isEnabled() and not dlg.zip_btn.isEnabled() and not dlg.times.isEnabled()
    dlg.checks["summary"].setChecked(True)
    dlg.zip_btn.click()
    assert dlg.result() and dlg.action == BundleDialog.ZIP and dlg.keys() == ["summary"]


def test_studio_offers_the_summary_and_the_action_items(tmp_path, monkeypatch):
    from echo_studio import actions, summary

    monkeypatch.delenv("ECHO_NO_EXTENSIONS", raising=False)
    extensions.loaded.cache_clear()
    try:
        rec = meeting(Library(tmp_path / "data"), "Weekly", [(1, "El precio sube.")], {1: "Ana"})
        assert bundle.available([rec]) == [("transcript", "Transcript")]
        rec.path(summary.FILE).write_text(json.dumps({"version": 1, "text": "# Precio\n- Sube en enero.",
                                                      "created": "2026-11-01T10:00:00"}))
        actions.add(rec, "Enviar el presupuesto", owner="Ana", due="2026-12-01", description="Con el precio nuevo.",
                    context="Lo pidió el cliente.", note="solo para mí")
        actions.add(rec, "Hecha")
        actions.add(rec, "Descartada")
        actions.set_done(rec, 1)
        actions.discard(rec, 2)
        assert bundle.available([rec]) == [("transcript", "Transcript"), ("summary", "Summary"),
                                           ("actions", "Action items")]
        note = bundle.render(rec, ["summary", "actions"])
        assert note.endswith("## Resumen\n\n### Precio\n- Sube en enero.\n\n## Acciones\n\n"
                             "- [ ] **Enviar el presupuesto** (Ana, 2026-12-01)\n  Con el precio nuevo.\n"
                             "  Lo pidió el cliente.\n- [x] **Hecha**\n")
        assert "solo para mí" not in note and "Descartada" not in note
    finally:
        extensions.loaded.cache_clear()

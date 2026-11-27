"""Collections: recordings filed apart from the day to day, in the files, the window and the command line."""

import json
import time

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from echo_app import bundle, cli, collections, importer, settings, watch
from echo_app.library import Library
from test_ui import lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures
from test_vault import _rec


def _names(found):
    return [(c.name, len(c.recordings)) for c in found]


def test_a_collection_is_a_field_of_its_recordings(tmp_path):
    library = Library(tmp_path / "data")
    a, b, c = _rec(library, "Uno"), _rec(library, "Dos"), _rec(library, "Tres")
    assert collections.all_of(library) == []
    assert collections.file([a, b], "  Entrevistas   2026 ") == 2
    assert json.loads(a.path("meta.json").read_text())["collection"] == "Entrevistas 2026"
    assert collections.file([a], "Entrevistas 2026") == 0  # already there
    # Names compare without case or accents; a new recording takes the spelling there is.
    assert collections.spelling(library, "entrevistas 2026") == "Entrevistas 2026"
    assert collections.get(library, "ENTREVISTAS 2026").recordings[0].id in (a.id, b.id)
    collections.file([c], "Curso")
    assert _names(collections.all_of(library)) == [("Curso", 1), ("Entrevistas 2026", 2)]
    found = collections.get(library, "Entrevistas 2026")
    assert found.transcribed == 2
    # Renaming onto another's name joins them; dissolving sends them back, deleting nothing.
    assert collections.rename(library, "Curso", "entrevistas 2026") == 1
    assert _names(collections.all_of(library)) == [("Entrevistas 2026", 3)]
    assert collections.rename(library, "Entrevistas 2026", "Entrevistas") == 3
    assert collections.dissolve(library, "entrevistas") == 3
    assert collections.all_of(library) == [] and len(library.all()) == 3


def test_an_old_recording_has_no_collection(tmp_path):
    library = Library(tmp_path / "data")
    rec = _rec(library)
    meta = json.loads(rec.path("meta.json").read_text())
    del meta["collection"]
    rec.path("meta.json").write_text(json.dumps(meta))
    assert library.get(rec.id).meta.collection == ""


def test_import_into_a_collection(tmp_path):
    library = Library(tmp_path / "data")
    files = [wav(tmp_path / f"e{k}.wav", 1, 300 + 50 * k) for k in range(3)]
    res = importer.import_paths(library, files[:2], auto_transcribe=False, collection="Entrevistas")
    assert [r.recording.meta.collection for r in res] == ["Entrevistas", "Entrevistas"]
    # A file already in the library stays where it is.
    res = importer.import_paths(library, files, auto_transcribe=False)
    assert [r.status for r in res] == [importer.DUPLICATE, importer.DUPLICATE, importer.IMPORTED]
    assert _names(collections.all_of(library)) == [("Entrevistas", 2)]


def _scan(scanner, folders, **kw):
    scanner.scan(folders, auto_transcribe=False, **kw)
    time.sleep(scanner.stable_seconds + 0.05)
    return scanner.scan(folders, auto_transcribe=False, **kw)


def test_a_watched_folders_subfolder_is_a_collection(tmp_path):
    library = Library(tmp_path / "data")
    folder = tmp_path / "inbox"
    (folder / "Curso de ventas" / "deeper").mkdir(parents=True)
    (folder / ".hidden").mkdir()
    wav(folder / "suelta.wav", 1, 300)
    wav(folder / "Curso de ventas" / "clase1.wav", 1, 400)
    wav(folder / "Curso de ventas" / "deeper" / "no.wav", 1, 500)
    wav(folder / ".hidden" / "no.wav", 1, 600)
    scanner = watch.Scanner(library, stable_seconds=0.2)
    # Off (the default): subfolders are not looked at, as before.
    assert [r.source.name for r in _scan(scanner, [folder]).imported] == ["suelta.wav"]
    assert collections.all_of(library) == []
    res = _scan(scanner, [folder], subfolders=True)
    assert [r.source.name for r in res.imported] == ["clase1.wav"]  # one level, nothing hidden
    assert _names(collections.all_of(library)) == [("Curso de ventas", 1)]
    # The setting is what a scan follows when not told, and a later file joins the same collection.
    cfg, _ = settings.load()
    cfg.watch_collections = True
    settings.save(cfg)
    (folder / "curso de ventas").mkdir(exist_ok=True)
    wav(folder / "Curso de ventas" / "clase2.wav", 1, 450)
    assert len(_scan(scanner, [folder]).imported) == 1
    assert _names(collections.all_of(library)) == [("Curso de ventas", 2)]
    assert not _scan(scanner, [folder]).imported  # not again


def test_command_line(tmp_path, capsys):
    cfg, _ = settings.load()
    library = Library(cfg.data_path)
    a, b, c = _rec(library, "Uno"), _rec(library, "Dos"), _rec(library, "Tres")
    b.update(created="2026-10-25T09:00:00-03:00")
    assert cli.main(["collections"]) == 0 and "No collections." in capsys.readouterr().out
    assert cli.main(["collections", a.id, b.id, "--add", "Entrevistas"]) == 0
    assert "2 recording(s) moved to Entrevistas" in capsys.readouterr().out
    assert cli.main(["collections"]) == 0 and "Entrevistas  (2 recordings)" in capsys.readouterr().out
    assert cli.main(["collections", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)["collections"]
    assert got == [{"name": "Entrevistas", "icon": None, "recordings": [b.id, a.id], "transcribed": 2}]
    assert cli.main(["list", "--collection", "entrevistas", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)["recordings"]
    assert {r["id"] for r in listed} == {a.id, b.id} and listed[0]["collection"] == "Entrevistas"
    assert cli.main(["list", "--collection", "", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)["recordings"]
    assert [r["id"] for r in listed] == [c.id] and listed[0]["collection"] is None
    assert cli.main(["list"]) == 0 and "[Entrevistas]" in capsys.readouterr().out
    assert cli.main(["bundle", "--collection", "Entrevistas"]) == 0
    assert capsys.readouterr().out == bundle.text([a, b])  # oldest first
    assert cli.main(["bundle", "--collection", "Nada"]) == 1 and cli.main(["bundle"]) == 2
    capsys.readouterr()
    f = wav(tmp_path / "nueva.wav", 1, 700)
    assert cli.main(["import", str(f), "--no-transcribe", "--collection", "ENTREVISTAS"]) == 0
    assert _names(collections.all_of(library)) == [("Entrevistas", 3)]
    assert cli.main(["collections", a.id, "--remove"]) == 0
    assert _names(collections.all_of(library)) == [("Entrevistas", 2)]
    assert cli.main(["collections", a.id]) == 2 and cli.main(["collections", "--add", "X"]) == 2
    assert cli.main(["collections", "nope", "--add", "X"]) == 1


def _titles(window):
    m = window.model
    return [r.meta.title for r in (m.recording(i) for i in range(m.rowCount())) if r]


def test_the_list_is_the_day_to_day_until_a_collection_is_opened(window, lib):
    a, b, c = _rec(lib, "Uno"), _rec(lib, "Dos"), _rec(lib, "Diaria")
    window._refresh()
    bar = window.collection_bar
    assert not bar.isVisible() and sorted(_titles(window)) == ["Diaria", "Dos", "Uno"]  # as it always was
    window._select(a.id)
    window.list.selectAll()
    window.list.selectionModel().select(window.model.index(window.model.row_of(c.id)),
                                        window.list.selectionModel().SelectionFlag.Deselect)
    window.file_selected("Entrevistas")
    assert "Moved 2 recordings to “Entrevistas”." in window.toast.text()
    assert bar.isVisible() and [r.title() for r in bar.rows] == ["Recordings", "Entrevistas"]
    assert [r.badge() for r in bar.rows] == ["1", "2"] and bar.rows[0].isChecked()
    assert _titles(window) == ["Diaria"]
    bar.rows[1].click()
    assert window.model.collection() == "Entrevistas" and sorted(_titles(window)) == ["Dos", "Uno"]
    assert window.current() is not None and window.current().meta.collection == "Entrevistas"
    # A search looks everywhere, wherever the list is.
    window.search.setText("Hola")
    assert wait_until(lambda: sorted(_titles(window)) == ["Diaria", "Dos", "Uno"])
    bar.rows[0].click()
    assert window.search.text() == "" and _titles(window) == ["Diaria"]
    # Sent to a recording filed elsewhere (a search result, an extension's page): its place opens.
    window.show_recording(a.id)
    assert window.model.collection() == "Entrevistas" and window.current().id == a.id and bar.rows[1].isChecked()
    window.show_recording(c.id)
    assert window.model.collection() is None and window.current().id == c.id
    # A transcript still to come shows as done/total.
    b.path("transcript.json").unlink()
    window._refresh()
    assert bar.rows[1].badge() == "1/2" and "1 of 2 transcribed" in bar.rows[1].toolTip()


def test_rename_dissolve_and_the_last_recording_leaving(window, lib, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    a, b = _rec(lib, "Uno"), _rec(lib, "Dos")
    collections.file([a, b], "Entrevistas")
    window._refresh()
    window.open_collection("Entrevistas")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Entrevistas 2026", True))
    window.rename_collection("Entrevistas")
    assert window.model.collection() == "Entrevistas 2026" and len(_titles(window)) == 2
    assert window.collection_bar.rows[1].isChecked()
    # Dragged onto Recordings: out of the collection.
    window._dropped_on_collection(None, [a.id])
    assert "back to Recordings" in window.toast.text() and _titles(window) == ["Dos"]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.dissolve_collection("Entrevistas 2026")
    assert window.model.collection() is None and not window.collection_bar.isVisible()
    assert sorted(_titles(window)) == ["Dos", "Uno"] and len(lib.all()) == 2
    # The menu offers the collections there are, a new one, and the way back.
    from PySide6.QtWidgets import QMenu

    collections.file([a], "Curso")
    window._refresh()
    window._select(b.id)
    menu = QMenu()
    window._collection_menu(menu)
    assert [x.text() for x in menu.actions()[0].menu().actions() if x.text()] == ["Curso", "New collection…"]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (" Otra ", True))
    window.file_selected_new()
    assert lib.get(b.id).meta.collection == "Otra"


def _drop(window, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    window.dropEvent(QDropEvent(QPointF(100, 100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier))


def test_a_dropped_batch_asks_for_a_collection(window, lib, tmp_path, monkeypatch):
    from echo_app.ui.collections import CollectionDialog

    asked = []

    def answer(name):
        def run(dlg):
            asked.append((dlg.combo.currentText(), [dlg.combo.itemText(i) for i in range(dlg.combo.count())]))
            dlg.name = name
            return 1 if name is not None else 0
        monkeypatch.setattr(CollectionDialog, "exec", run)

    # One file is the day to day: no question.
    answer("never")
    _drop(window, [wav(tmp_path / "sola.wav", 1, 250)])
    assert wait_until(lambda: window.model.total == 1) and not asked
    # A folder of files: asked once, its name offered.
    batch = tmp_path / "Entrevistas"
    batch.mkdir()
    for k in range(3):
        wav(batch / f"e{k}.wav", 1, 300 + 40 * k)
    answer("Entrevistas")
    _drop(window, [batch])
    assert wait_until(lambda: window.model.total == 4)
    assert asked == [("Entrevistas", [])]
    assert wait_until(lambda: "Imported 3 into “Entrevistas”" in window.toast.text())
    # The collection opens with what came in, and the day-to-day list did not grow.
    assert window.model.collection() == "Entrevistas" and len(_titles(window)) == 3
    assert window.collection_bar.rows[0].badge() == "1"
    # With a collection open, files go into it without a question.
    more = [wav(tmp_path / f"m{k}.wav", 1, 600 + 40 * k) for k in range(2)]
    _drop(window, more)
    assert wait_until(lambda: len(_titles(window)) == 5) and len(asked) == 1
    # Back in the day to day: "Just import", then Cancel.
    window.open_collection(None)
    answer("")
    _drop(window, [wav(tmp_path / f"d{k}.wav", 1, 800 + 40 * k) for k in range(2)])
    assert wait_until(lambda: window.model.total == 8)
    assert asked[-1] == ("", ["Entrevistas"]) and window.model.collection() is None and len(_titles(window)) == 3
    answer(None)
    _drop(window, [wav(tmp_path / f"c{k}.wav", 1, 900 + 20 * k) for k in range(2)])
    pump(600)
    assert window.model.total == 8
    # Dropped on a collection's row: into it.
    window.collection_bar.files_dropped.emit("Entrevistas", [wav(tmp_path / "fila.wav", 1, 1000)])
    assert wait_until(lambda: len(collections.get(lib, "Entrevistas").recordings) == 6)


def test_the_dialog(qapp):
    from echo_app.ui.collections import CollectionDialog

    dlg = CollectionDialog(12, ["Curso", "Entrevistas"])
    assert not dlg.file_btn.isEnabled() and dlg.file_btn.isDefault()
    dlg.combo.setEditText("  Clientes   2026 ")
    assert dlg.file_btn.isEnabled()
    dlg.file_btn.click()
    assert dlg.result() and dlg.name == "Clientes 2026"
    dlg = CollectionDialog(12, ["Curso"], "Curso")
    dlg.plain_btn.click()
    assert dlg.result() and dlg.name == ""


def test_bundle_a_collection(window, lib, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from echo_app.ui.dialogs import BundleDialog

    a, b = _rec(lib, "Uno"), _rec(lib, "Dos")
    b.update(created="2026-10-25T09:00:00-03:00")
    collections.file([a, b], "Entrevistas")
    window._refresh()
    monkeypatch.setattr(BundleDialog, "exec", lambda dlg: 1)
    window.bundle_collection("Entrevistas")
    assert wait_until(lambda: "Copied 2 recordings" in window.toast.text())
    assert QApplication.clipboard().text() == bundle.text([a, b])


def test_settings_page_has_the_subfolders_option(qapp):
    from echo_app.ui.dialogs import WatchedFoldersPage

    on, off = WatchedFoldersPage(["/tmp/x"], True), WatchedFoldersPage([])
    assert on.subfolders.isChecked() and not off.subfolders.isChecked()
    # Destroyed here: a list widget left for the interpreter's exit outlives the application and
    # crashed the test process after its last test (exit code 135 with every test passed).
    for page in (on, off):
        page.deleteLater()
    pump(50)


def test_studio_keeps_an_imported_batch_out_of_the_day_to_day(tmp_path):
    from echo_studio import actions

    library = Library(tmp_path / "data")
    daily, batch = _rec(library, "Diaria"), _rec(library, "Archivada")
    mine = library.create("Reunión IHSA", "recorded")
    collections.file([batch], "Curso")
    collections.file([mine], "IHSA")
    assert collections.apart(batch) and not collections.apart(mine) and not collections.apart(daily)
    actions.add(daily, "Llamar a Ana")
    actions.add(batch, "Repasar la clase")
    actions.add(mine, "Enviar el informe")
    # A meeting the user recorded is their day's work wherever it is filed; an imported batch is not.
    assert {i["text"] for i in actions.open_items(library)} == {"Llamar a Ana", "Enviar el informe"}
    assert [i["text"] for i in actions.load(batch)["items"]] == ["Repasar la clase"]  # still its own


def test_new_recordings_go_where_chosen(window, lib, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    panel = window.recorder_panel
    assert panel.destination() == "" and panel.dest_btn.text() == "Into Recordings" and panel.dest_btn.isVisible()
    # Chosen before anything is in it: the first recording makes the collection.
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("  IHSA ", True))
    panel._new_destination()
    assert panel.destination() == "IHSA" and panel.dest_btn.text() == "Into IHSA"
    assert settings.load()[0].record_collection == "IHSA"
    panel._fill_destinations()
    entries = [(a.text(), a.isChecked()) for a in panel.dest_menu.actions() if a.text()]
    assert entries == [("Recordings (day to day)", False), ("IHSA", True), ("New collection…", False)]
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    rid = panel.session.rec.id
    assert lib.get(rid).meta.collection == "IHSA" and not panel.dest_btn.isVisible()  # filed from the start
    pump(600)
    panel.stop()
    assert wait_until(lambda: lib.get(rid) is not None and lib.get(rid).meta.state == "ready", 20)
    window._refresh()
    assert [(c.name, len(c.recordings)) for c in collections.all_of(lib)] == [("IHSA", 1)]
    assert window.model.collection() == "IHSA" and window.current().id == rid  # shown where it went
    # A quick note is not filed; the collection's menu switches the choice, and it follows a rename.
    panel.start(quick_note=True)
    assert wait_until(lambda: panel.session is not None)
    note = panel.session.rec.id
    assert lib.get(note).meta.collection == ""
    pump(600)
    panel.stop()
    assert wait_until(lambda: lib.get(note) is None or lib.get(note).meta.state == "ready", 20)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("IHSA 2026", True))
    window.rename_collection("IHSA")
    assert panel.destination() == "IHSA 2026" and panel.dest_btn.text() == "Into IHSA 2026"
    panel.set_destination("")
    assert panel.destination() == "" and settings.load()[0].record_collection == ""


def test_record_from_the_command_line_follows_the_choice(tmp_path, capsys):
    from echo_app import recorder

    cfg, _ = settings.load()
    library = Library(cfg.data_path)
    collections.set_for_new("IHSA")
    for args, where in (([], "IHSA"), (["--collection", ""], ""), (["--collection", "Otra"], "Otra")):
        assert cli.main(["record", *args]) == 0
        assert (", into " + where if where else "default input\n") in capsys.readouterr().out or not where
        sess = recorder.active(library)
        assert sess.rec.meta.collection == where
        time.sleep(0.4)
        assert cli.main(["stop"]) == 0
        capsys.readouterr()


def test_icons_for_recordings_and_collections(tmp_path, capsys):
    from echo_app.ui import theme

    cfg, _ = settings.load()
    library = Library(cfg.data_path)
    a, b = _rec(library, "Uno"), _rec(library, "Dos")
    assert collections.clean_icon("  Target:Coral \n") == "target:coral" and collections.clean_icon("") == ""
    assert collections.clean_icon("🏥") == "" and collections.clean_icon("a b") == ""  # not a symbol's name
    assert collections.icon_parts("target:coral") == ("target", "coral")
    assert collections.icon_parts("target:nope") == ("target", "") and collections.icon_parts("") == ("", "")
    # Every symbol offered is bundled, and every color is one the theme has.
    assert len(collections.ICONS) == 40 and len(set(collections.ICONS)) == 40
    assert all(theme._svg(name) for name in collections.ICONS)
    assert all(hasattr(theme.current(), role) for role in collections.COLORS if role)
    a.update(icon="target:coral")
    assert library.get(a.id).meta.icon == "target:coral" and library.get(b.id).meta.icon == ""
    collections.file([a, b], "IHSA")
    assert collections.get(library, "IHSA").icon == ""
    collections.set_icon(library, "ihsa", "hospital:foam")
    assert collections.get(library, "IHSA").icon == "hospital:foam"
    assert json.loads((library.data_dir / collections.LOOKS).read_text()) == {"icons": {"ihsa": "hospital:foam"}}
    assert cli.main(["collections", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["collections"][0]["icon"] == "hospital:foam"
    assert cli.main(["info", a.id, "--json"]) == 0 and '"icon": "target:coral"' in capsys.readouterr().out
    # The icon goes with a rename, and away when the collection does; a broken file is no icons.
    collections.rename(library, "IHSA", "IHSA 2026")
    assert collections.get(library, "IHSA 2026").icon == "hospital:foam" and "ihsa" not in collections.icons(library)
    collections.dissolve(library, "IHSA 2026")
    assert collections.icons(library) == {}
    (library.data_dir / collections.LOOKS).write_text("{nope")
    assert collections.icons(library) == {} and collections.all_of(library) == []


def _lit(image, color) -> int:
    """How many pixels of a grab are close to a color: whether something was drawn in it."""
    from PySide6.QtGui import QColor

    want = QColor(color)
    img = image.toImage()
    return sum(1 for x in range(img.width()) for y in range(img.height())
               if abs(img.pixelColor(x, y).red() - want.red()) + abs(img.pixelColor(x, y).green() - want.green())
               + abs(img.pixelColor(x, y).blue() - want.blue()) < 40)


def test_icons_in_the_window(window, lib, monkeypatch):
    from echo_app.ui import theme
    from echo_app.ui.collections import IconPicker

    a, b = _rec(lib, "Uno"), _rec(lib, "Dos")
    collections.file([a], "IHSA")
    window._refresh()
    window.open_collection("IHSA")
    answers = iter(["target:coral", "hospital:lime", None, ""])
    asked = []

    def ask(what, current="", parent=None):
        asked.append((what, current))
        return next(answers)

    monkeypatch.setattr(IconPicker, "ask", ask)
    window._select(a.id)
    coral, lime = theme.current().coral, theme.current().lime
    assert _lit(window.list.grab(), coral) == 0
    window.pick_icon()
    assert lib.get(a.id).meta.icon == "target:coral"
    assert _lit(window.list.grab(), coral) > 20  # the row shows its symbol, in its color
    assert _lit(window.collection_bar.grab(), lime) == 0
    window.pick_collection_icon("IHSA")
    row = window.collection_bar.rows[1]
    assert row.icon == "hospital:lime" and asked == [("“Uno”", ""), ("“IHSA”", "")]
    assert _lit(window.collection_bar.grab(), lime) > 20
    window.recorder_panel.set_destination("IHSA")
    assert window.recorder_panel.dest_btn.text() == "Into IHSA"
    assert _lit(window.recorder_panel.dest_btn.grab(), lime) > 10  # the collection's own icon
    window.pick_icon()  # cancelled: kept
    assert lib.get(a.id).meta.icon == "target:coral" and asked[-1] == ("“Uno”", "target:coral")
    window.pick_icon()  # "No icon"
    assert lib.get(a.id).meta.icon == "" and _lit(window.list.grab(), coral) == 0


def test_the_icon_picker(qapp):
    from echo_app.ui.collections import IconPicker

    dlg = IconPicker("“IHSA”", "hospital:coral")
    assert [n for n, b in dlg.buttons.items() if b.isChecked()] == ["hospital"]
    assert dlg.swatches["coral"].isChecked() and dlg.none_btn.isEnabled()
    dlg.swatches["amber"].click()
    dlg.buttons["rocket"].click()
    assert dlg.result() and dlg.icon == "rocket:amber"
    dlg2 = IconPicker("3 recordings")
    assert not dlg2.none_btn.isEnabled() and dlg2.swatches[""].isChecked()
    dlg2.buttons["star"].click()
    assert dlg2.result() and dlg2.icon == "star"  # no color: the text's
    dlg3 = IconPicker("“IHSA”", "star:lime")
    dlg3.none_btn.click()
    assert dlg3.result() and dlg3.icon == ""
    for d in (dlg, dlg2, dlg3):
        d.deleteLater()
    pump(50)

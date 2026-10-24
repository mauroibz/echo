"""The dictionary in the window: the candidate chip, underlined corrections, undo, settings page."""

import json

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMenu

from echo_app import dictionary as D
from echo_app import importer
from echo_app.library import CORRECTED, TRANSCRIPT
from test_ui import lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures


def _with_text(lib, tmp_path, texts, freq=440):
    rec = importer.import_file(lib, wav(tmp_path / f"t{freq}.wav", 4, freq)).recording
    segs = [{"start": i * 2.0, "end": i * 2.0 + 1.5, "text": t, "paragraph": True} for i, t in enumerate(texts)]
    rec.path(TRANSCRIPT).write_text(json.dumps({"text": "\n\n".join(texts), "segments": segs,
                                                "created": "2026-10-23T10:00:00-03:00",
                                                "model": {"adapter_enabled": True}}))
    return rec


def _replace(editor, old, new):
    text = editor.toPlainText()
    i = text.index(old)
    cur = editor.textCursor()
    cur.setPosition(i)
    cur.setPosition(i + len(old), QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cur)
    editor.insertPlainText(new)


def test_correcting_a_name_offers_it_and_accepting_adds_it(window, lib, tmp_path):
    rec = _with_text(lib, tmp_path, ["Mañana veo a zurus en la oficina.", "Después hablamos."])
    other = _with_text(lib, tmp_path, ["El equipo de zurus ganó."], freq=600)
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    _replace(tp.editor, "zurus", "Surus")
    tp.save()
    assert tp.chip.isVisibleTo(tp) and "Surus" in tp.chip_text.text() and "zurus" in tp.chip_text.text()
    tp.chip_add.click()
    assert not tp.chip.isVisibleTo(tp)
    entry = D.load().find("Surus")
    assert entry is not None and entry.aliases == ["zurus"]
    # The other recording is corrected when shown, with the spot underlined and undoable.
    window._select(other.id)
    assert wait_until(lambda: tp.editor.toPlainText() == "El equipo de Surus ganó.", 3)
    assert other.path(CORRECTED).exists() and "1 name corrected" in tp.status.text()
    assert len(tp._corrections) == 1
    a, b, edit = tp._corrections[0]
    assert tp.editor.toPlainText()[a:b] == "Surus"
    menu = QMenu()
    tp._menu_hook(menu, a + 1)
    undo = [act for act in menu.actions() if act.text().startswith("Undo this correction")]
    assert undo
    undo[0].trigger()
    assert wait_until(lambda: tp.editor.toPlainText() == "El equipo de zurus ganó.", 3)
    assert other.text() == "El equipo de zurus ganó."


def test_declining_mutes_the_word(window, lib, tmp_path):
    rec = _with_text(lib, tmp_path, ["Hoy vino pepe a casa."])
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    _replace(tp.editor, "pepe", "Pepe")
    tp.save()
    assert tp.chip.isVisibleTo(tp)
    tp.chip_no.click()
    assert D.load().is_muted("Pepe") and not tp.chip.isVisibleTo(tp)
    _replace(tp.editor, "casa", "casa grande")
    tp.save()
    assert not tp.chip.isVisibleTo(tp)


def test_renaming_offers_names_from_the_title(window, lib, tmp_path):
    rec = _with_text(lib, tmp_path, ["Hola a todos."])
    window._select(rec.id)
    pump(100)
    window.player.title.setText("Entrevista con Lucía Fernández")
    window.player._commit_title()
    tp = window.transcript
    assert tp.chip.isVisibleTo(tp) and "Lucía Fernández" in tp.chip_text.text()
    assert "person" in tp.chip_text.text()


def test_context_line_is_saved_and_used(window, lib, tmp_path, monkeypatch):
    rec = _with_text(lib, tmp_path, ["Hola."])
    window._select(rec.id)
    pump(100)
    window.player.context.setText("Charla con Ana sobre el proyecto")
    window.player._commit_context()
    assert lib.get(rec.id).meta.context_line == "Charla con Ana sobre el proyecto"
    from echo_app import transcription

    assert transcription.build_context(lib.get(rec.id)) == "Charla con Ana sobre el proyecto."


def test_settings_dictionary_page_remove_and_merge(qapp, lib, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from echo_app.ui.dialogs import SettingsDialog

    D.update(lambda d: (d.add(D.PEOPLE, "Lucía Fernández"), d.add(D.PEOPLE, "Lucia", ["Luci"]),
                        d.add(D.TERMS, "Surus")))
    dlg = SettingsDialog(recording_active=False)
    page = dlg.dictionary
    assert page.tree.topLevelItemCount() == 3
    for i in range(3):
        it = page.tree.topLevelItem(i)
        it.setSelected(it.text(0) in ("Lucía Fernández", "Lucia"))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Lucía Fernández", True))
    page._merge()
    for i in range(page.tree.topLevelItemCount()):
        it = page.tree.topLevelItem(i)
        it.setSelected(it.text(0) == "Surus")
    page._remove()
    dlg.accept()
    d = D.load()
    assert [e.name for e in d.entries] == ["Lucía Fernández"] and d.entries[0].aliases == ["Lucia", "Luci"]

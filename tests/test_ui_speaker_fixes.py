"""Said by in the editor: relabel a paragraph, split off an interruption, undo, join, someone new."""

from PySide6.QtWidgets import QMenu

from echo_app import export
from test_speaker_fixes import _ana_pedro
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures


def _labels(tp):
    return [name for _a, name, _c, _n in tp.editor.margin.labels]


def _open(window, lib):
    rec = _ana_pedro(lib)
    window.model.refresh()
    window._select(rec.id)
    pump(200)
    return rec, window.transcript


def test_split_off_an_interruption_and_undo(window, lib):
    rec, tp = _open(window, lib)
    assert _labels(tp) == ["Ana", "Pedro"]
    text = tp.editor.toPlainText()
    s = text.index("¿cuánto?")
    menu = QMenu()
    cur = tp.editor.textCursor()
    cur.setPosition(s)
    cur.setPosition(s + len("¿cuánto?"), cur.MoveMode.KeepAnchor)
    tp.editor.setTextCursor(cur)
    tp._menu_hook(menu, s + 2)
    said = next(a for a in menu.actions() if a.text() == "Said by")
    assert [a.text() for a in said.menu().actions() if a.text()] == ["Ana (speaker 1)", "Pedro (speaker 2)", "Someone else…"]
    next(a for a in said.menu().actions() if a.text().startswith("Pedro")).trigger()
    assert tp.editor.toPlainText().startswith("El precio sube\n\n¿cuánto?\n\nun diez por ciento.")
    assert _labels(tp) == ["Ana", "Pedro", "Ana", "Pedro"]
    assert wait_until(lambda: lib.get(rec.id).is_edited(), 5)
    assert export.render_transcript(lib.get(rec.id), ".txt").startswith(
        "Ana: El precio sube\n\nPedro: ¿cuánto?\n\nAna: un diez por ciento.")
    pos = tp.editor.toPlainText().index("¿cuánto?") + 1
    menu = QMenu()
    tp._menu_hook(menu, pos)
    assert any(a.text() == "Back to the speaker Echo found" for a in menu.actions())
    tp.unfix_at(pos)
    assert _labels(tp) == ["Ana", "Pedro"] and lib.get(rec.id).fixes() == []


def test_relabel_a_paragraph_join_and_someone_else(window, lib, monkeypatch):
    rec, tp = _open(window, lib)
    pos = tp.editor.toPlainText().index("Sigo yo.") + 1
    tp.said_by(1, None, pos)
    assert _labels(tp) == ["Ana", "Pedro", "Ana"]
    assert "3 speakers" not in tp.status.text()
    tp.join_above(pos)
    assert tp.editor.toPlainText().endswith("Bien. Sigo yo.")
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Luis", True))
    pos = tp.editor.toPlainText().index("Bien.") + 1
    tp._said_by_someone_else(None, pos)
    r = lib.get(rec.id)
    assert r.meta.speakers.get("3") == "Luis" and 3 in r.speaker_numbers()
    assert "Luis" in _labels(tp)

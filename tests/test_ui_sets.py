"""Linked sets in the window: the list rows, the stacked transcript, linking, unlinking, dragging."""

import json

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from echo_app import importer, sets
from echo_app.library import EDITED, TRANSCRIPT
from echo_app.worker.planning import join_text
from test_ui import lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures

TEXTS = [["Hola, te cuento.", "El envío llegó tarde."], ["Y vino incompleto."], ["Avisame cuando sepas."]]



def _items(model):
    """The list's rows without its date headings."""
    return [r for r in model._rows if not r.startswith("§")]

def _parts(lib, tmp_path, n=3):
    out = []
    for k, texts in enumerate(TEXTS[:n]):
        rec = importer.import_file(lib, wav(tmp_path / f"PTT-20261023-WA000{k + 4}.wav", 4, 300 + 100 * k)).recording
        rec.update(created=f"2026-10-23T14:0{2 + 2 * k}:00-03:00", title=f"Nota {k + 1}")
        segs = [{"start": i * 2.0, "end": i * 2.0 + 1.8, "text": t, "paragraph": i == 0} for i, t in enumerate(texts)]
        rec.path(TRANSCRIPT).write_text(json.dumps({"segments": segs, "text": join_text(segs), "language": "es"}))
        out.append(rec)
    return out


def _linked(window, lib, tmp_path):
    parts = _parts(lib, tmp_path)
    other = importer.import_file(lib, wav(tmp_path / "otra.wav", 2, 700)).recording
    st = sets.link(lib, [r.id for r in parts], title="Proveedor")
    window.model.reload_sets()
    window._select(st.id)
    pump(150)
    return st, parts, other


def _body_pos(tp, k: int) -> int:
    return tp._bodies()[k][0]


def test_set_row_shows_the_parts_stacked_and_on_one_timeline(window, lib, tmp_path):
    st, parts, other = _linked(window, lib, tmp_path)
    m = window.model
    assert _items(m) == [other.id, st.id]  # one row for the set, placed by its newest part
    assert window.current_set()[0].id == st.id and window.current() is None
    tp = window.transcript
    text = tp.editor.toPlainText()
    assert text.startswith("1  ·  Nota 1  ·  ") and "\nHola, te cuento. El envío llegó tarde.\n\n2  ·  Nota 2" in text
    assert text.endswith("\nAvisame cuando sepas.")
    assert "3 parts" in tp.status.text()
    assert window.player.linked.id == st.id and window.player.player.duration == 12.0
    assert window.player.wave.dividers == [4.0, 8.0] and not window.player.wave.editable
    assert window.player.title.text() == "Proveedor"
    # Passages are on the set's timeline: the second part's first passage starts at 4 s.
    assert [round(t, 1) for _a, _b, t in tp._spans] == [0.0, 2.0, 4.0, 8.0]
    tp.follow(4.5)
    a, _b, _t = tp._spans[tp._current_span]
    assert tp.editor.toPlainText()[a:].startswith("Y vino incompleto.")
    seeks = []
    tp.seek_requested.connect(seeks.append)
    tp._on_ctrl_click(_body_pos(tp, 2) + 3)
    assert seeks == [8.0]


def test_expanding_shows_parts_and_a_part_alone(window, lib, tmp_path):
    st, parts, other = _linked(window, lib, tmp_path)
    m = window.model
    rect = window.list.visualRect(m.index(m.row_of(st.id)))
    QTest.mouseClick(window.list.viewport(), Qt.MouseButton.LeftButton, pos=window.delegate.chevron_rect(rect).center())
    assert _items(m) == [other.id, st.id, *[r.id for r in parts]]
    assert window.current_set()[0].id == st.id  # still selected after the list was rebuilt
    window._select(parts[1].id)
    pump(100)
    assert window.current().id == parts[1].id and window.transcript.linked is None
    assert window.transcript.editor.toPlainText() == "Y vino incompleto."
    # Left on a part goes to its set; Left on the set folds it.
    QTest.keyClick(window.list, Qt.Key.Key_Left)
    assert window.current_set()[0].id == st.id
    QTest.keyClick(window.list, Qt.Key.Key_Left)
    assert _items(m) == [other.id, st.id]
    QTest.keyClick(window.list, Qt.Key.Key_Right)
    assert len(_items(m)) == 5 and window.model.expanded == {st.id}


def test_editing_a_part_saves_only_that_part(window, lib, tmp_path):
    st, parts, _other = _linked(window, lib, tmp_path)
    tp = window.transcript
    c = tp.editor.textCursor()
    c.setPosition(tp._bodies()[1][1])  # end of the second part's text
    tp.editor.setTextCursor(c)
    tp.editor.setFocus()
    QTest.keyClicks(tp.editor, " Faltan dos cajas.")
    assert wait_until(lambda: parts[1].path(EDITED).exists(), 3)
    assert parts[1].path(EDITED).read_text() == "Y vino incompleto. Faltan dos cajas."
    assert not parts[0].path(EDITED).exists() and not parts[2].path(EDITED).exists()
    # Selecting the part alone shows the correction.
    window.model.set_expanded(st.id, True)
    window._select(parts[1].id)
    pump(100)
    assert window.transcript.editor.toPlainText() == "Y vino incompleto. Faltan dos cajas."
    # Back on the set, the edit is there and putting the text back removes the edited copy.
    window._select(st.id)
    pump(100)
    tp = window.transcript
    assert "Y vino incompleto. Faltan dos cajas." in tp.editor.toPlainText()
    b = tp._bodies()[1]
    c = tp.editor.textCursor()
    c.setPosition(b[1] - len(" Faltan dos cajas."))
    c.setPosition(b[1], QTextCursor.MoveMode.KeepAnchor)
    tp.editor.setTextCursor(c)
    QTest.keyClick(tp.editor, Qt.Key.Key_Delete)
    assert wait_until(lambda: not parts[1].path(EDITED).exists(), 3)


def test_headings_cannot_be_edited_or_crossed(window, lib, tmp_path):
    _st, parts, _other = _linked(window, lib, tmp_path)
    tp = window.transcript
    ed = tp.editor
    before = ed.toPlainText()
    ed.setFocus()

    def at(pos, anchor=None):
        c = ed.textCursor()
        c.setPosition(anchor if anchor is not None else pos)
        c.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(c)

    second = tp._bodies()[1]
    at(tp._bodies()[0][1] - 3, second[0] + 3)  # from the end of part 1 into part 2
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    QTest.keyClicks(ed, "x")
    at(second[0])  # start of part 2's text
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    at(second[0] - 3)  # inside the heading
    QTest.keyClicks(ed, "abc")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    at(tp._bodies()[0][1])  # end of part 1's text: Delete would join the blank line
    QTest.keyClick(ed, Qt.Key.Key_Delete)
    QApplication.clipboard().setText("pegado")
    at(tp._bodies()[0][1] - 3, second[0] + 3)
    QTest.keySequence(ed, "Ctrl+V")
    pump(50)
    assert ed.toPlainText() == before
    # Typing at the very start of a part's text is fine.
    at(second[0])
    QTest.keyClicks(ed, "Bueno. ")
    assert ed.toPlainText().count("Bueno. Y vino incompleto.") == 1
    # The last guard: an edit that bypasses the keys (an input method) is undone, and nothing is saved.
    c = ed.textCursor()
    c.setPosition(tp._bodies()[1][0] - 2)
    c.setPosition(tp._bodies()[1][0] + 2, QTextCursor.MoveMode.KeepAnchor)
    c.insertText("")
    assert wait_until(lambda: tp._structure_ok(), 2)
    tp.save()
    assert not parts[0].path(EDITED).exists()


def test_link_from_a_selection_then_unlink(window, lib, tmp_path):
    parts = _parts(lib, tmp_path, 2)
    window.model.refresh()
    sm = window.list.selectionModel()
    from PySide6.QtCore import QItemSelectionModel

    window.list.setCurrentIndex(window.model.index(window.model.row_of(parts[0].id)))
    sm.select(window.model.index(window.model.row_of(parts[1].id)), QItemSelectionModel.SelectionFlag.Select)
    pump(50)
    assert window.selection_bar.isVisible() and window.selection_label.text() == "2 selected"
    window.link_btn.click()
    pump(100)
    st = sets.set_of(lib, parts[0].id)
    assert st.members == [parts[0].id, parts[1].id]
    assert window.current_set()[0].id == st.id and not window.selection_bar.isVisible()
    window.unlink_set(st.id)
    assert sets.load_all(lib) == [] and _items(window.model) == [parts[1].id, parts[0].id]


def _drop(window, ids, pos: QPoint):
    md = QMimeData()
    md.setData(window.model.MIME, "\n".join(ids).encode())
    vp = window.list.viewport()
    actions = Qt.DropAction.MoveAction
    for ev in (QDragEnterEvent(QPointF(pos), actions, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
               QDragMoveEvent(QPointF(pos), actions, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
               QDropEvent(QPointF(pos), actions, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)):
        QApplication.sendEvent(vp, ev)
    pump(100)


def test_dragging_links_reorders_and_unlinks(window, lib, tmp_path):
    a, b, c = _parts(lib, tmp_path)
    window.model.refresh()
    m = window.model

    def rect(rid):
        return window.list.visualRect(m.index(m.row_of(rid)))

    _drop(window, [a.id], rect(b.id).center())  # onto a row: link the two
    st = sets.set_of(lib, a.id)
    assert st is not None and st.members == [a.id, b.id]
    _drop(window, [c.id], rect(st.id).center())  # onto the set: add at the end
    assert sets.get(lib, st.id).members == [a.id, b.id, c.id]
    m.set_expanded(st.id, True)
    pump(50)
    _drop(window, [c.id], rect(a.id).topLeft() + QPoint(40, 2))  # between the set row and part 1
    assert sets.get(lib, st.id).members == [c.id, a.id, b.id]
    _drop(window, [b.id], rect(st.id).topLeft() + QPoint(40, 1))  # above the set: out of it
    assert sets.get(lib, st.id).members == [c.id, a.id] and sets.set_of(lib, b.id) is None


def test_keyboard_moves_a_part(window, lib, tmp_path):
    st, parts, _other = _linked(window, lib, tmp_path)
    window.model.set_expanded(st.id, True)
    window._select(parts[0].id)
    window.a_part_down.trigger()
    assert sets.get(lib, st.id).members == [parts[1].id, parts[0].id, parts[2].id]
    assert window.current().id == parts[0].id
    window.a_part_up.trigger()
    assert sets.get(lib, st.id).members == [r.id for r in parts]


def test_deleting_a_set_unlinks_by_default(window, lib, tmp_path):
    st, parts, _other = _linked(window, lib, tmp_path)
    QTimer.singleShot(200, lambda: QApplication.activeModalWidget().defaultButton().click())
    window.delete_selected()
    assert sets.get(lib, st.id) is None and all(lib.get(r.id) for r in parts)


def test_heading_click_opens_the_part_and_search_finds_in_a_set(window, lib, tmp_path):
    st, parts, _other = _linked(window, lib, tmp_path)
    tp = window.transcript
    tp.editor.heading_clicked.emit(2)
    pump(100)
    assert window.current().id == parts[2].id and window.model.is_expanded(st.id)
    window.model.set_expanded(st.id, False)
    window._select(st.id)
    pump(100)
    window.search.setText("incompleto")
    assert wait_until(lambda: window.transcript.findbar.isVisible())
    tp = window.transcript
    a, b = tp._find_matches[tp._find_index]
    assert tp.editor.toPlainText()[a:b] == "incompleto"
    # While searching, the set shows the part that matches.
    assert _items(window.model)[-1] == parts[1].id


def test_set_copy_and_title(window, lib, tmp_path):
    st, parts, _other = _linked(window, lib, tmp_path)
    window.transcript.copy_all()
    text = QApplication.clipboard().text()
    assert text.startswith("Nota 1 · 2026-10-23 14:02 · 0:04\n\nHola, te cuento.") and "Avisame cuando sepas." in text
    window.player.title.setText("Proveedor de cajas")
    window.player.title.editingFinished.emit()
    assert sets.get(lib, st.id).title == "Proveedor de cajas" and not sets.get(lib, st.id).title_auto
    window.player.context.setText("Charla con Lucía")
    window.player.context.editingFinished.emit()
    assert all(lib.get(r.id).meta.context_line == "Charla con Lucía" for r in parts)


def test_flags_passage_play_and_names_work_across_parts(window, lib, tmp_path, monkeypatch):
    from echo_app.audio.playback import Playback

    st, parts, _other = _linked(window, lib, tmp_path)
    # Part 2's passage was flagged by the model.
    t = json.loads(parts[1].path(TRANSCRIPT).read_text())
    t["segments"][0]["flags"] = ["low"]
    parts[1].path(TRANSCRIPT).write_text(json.dumps(t))
    window._refresh()
    pump(100)
    tp = window.transcript
    assert [tp.editor.toPlainText()[a:b] for a, b, _s in tp._flagged] == ["Y vino incompleto."]
    assert "⚑ 1 passage to check" in tp.status.text()
    # Ctrl+. in part 3 plays that part's own audio, from its own times.
    calls = []

    def play(self, start=None, end=None):
        calls.append((self.path.parent.name, round(start, 2), round(end, 2)))
        self._out = object()

    monkeypatch.setattr(Playback, "play", play)
    monkeypatch.setattr(Playback, "pause", lambda self: setattr(self, "_out", None))
    monkeypatch.setattr(Playback, "poll", lambda self: False)
    c = tp.editor.textCursor()
    c.setPosition(_body_pos(tp, 2) + 2)
    tp.editor.setTextCursor(c)
    tp.play_passage()
    assert calls == [(parts[2].id, 0.0, 1.8)]
    # A name corrected in a part is offered for the dictionary.
    start = tp.editor.toPlainText().index("envío")
    c.setPosition(start)
    c.setPosition(start + len("envío"), QTextCursor.MoveMode.KeepAnchor)
    tp.editor.setTextCursor(c)
    tp.editor.insertPlainText("Mercurio")
    tp.save()
    assert parts[0].path(EDITED).read_text() == "Hola, te cuento. El Mercurio llegó tarde."
    assert not tp.chip.isHidden() and "Mercurio" in tp.chip_text.text()


def test_a_part_without_text_and_markers_on_the_set_timeline(window, lib, tmp_path):
    parts = _parts(lib, tmp_path, 2)
    bare = importer.import_file(lib, wav(tmp_path / "PTT-20261023-WA0009.wav", 3, 900)).recording
    bare.update(created="2026-10-23T14:09:00-03:00")
    parts[1].set_markers([{"at": 1.0, "note": "ojo"}])
    st = sets.link(lib, [*(r.id for r in parts), bare.id])
    window.model.reload_sets()
    window._select(st.id)
    pump(150)
    tp = window.transcript
    text = tp.editor.toPlainText()
    assert text.endswith("Not transcribed yet: select this part to transcribe it")
    assert tp._bodies()[2] is None and "1 without text yet" in tp.status.text()
    end = len(text)
    c = tp.editor.textCursor()
    c.setPosition(end)
    tp.editor.setTextCursor(c)
    QTest.keyClicks(tp.editor, "x")
    assert tp.editor.toPlainText() == text  # the state line is not editable
    assert window.player.wave.markers == [{"at": 5.0, "note": "ojo"}]  # part 2 starts at 4 s
    assert [m["at"] for _pos, m in tp._marker_anchors()] == [5.0]


def test_importing_a_burst_offers_to_link_it(window, lib, tmp_path):
    files = [wav(tmp_path / f"PTT-20261023-WA000{n}.opus", 1, 300 + 50 * n) for n in (4, 5, 6)]
    window.import_paths(files)
    assert wait_until(lambda: window.banner.isVisible(), 10)
    assert "3 voice notes from 23 Oct" in window.banner_text.text() and window.banner_link.text() == "Link them"
    window.banner_text.linkActivated.emit("#")
    assert len(window._selected_keys()) == 3
    window.banner_link.click()
    pump(100)
    st = sets.load_all(lib)[0]
    assert len(st.members) == 3 and window.current_set()[0].id == st.id and not window.banner.isVisible()
    # A dismissed offer is not shown again.
    more = [wav(tmp_path / f"PTT-20261023-WA001{n}.opus", 1, 900 + 50 * n) for n in (1, 2)]
    window.import_paths(more)
    assert wait_until(lambda: window.banner.isVisible(), 10)
    window.banner_close.click()
    assert not window.banner.isVisible()
    window._got_offers(sets.bursts(lib, [r.id for r in lib.all() if r.meta.source.startswith("PTT-20261023-WA001")]))
    assert not window.banner.isVisible()


def test_a_watched_folder_note_is_offered_to_its_set(window, lib, tmp_path):
    from echo_app import watch

    first = [importer.import_file(lib, wav(tmp_path / f"PTT-20261023-WA000{n}.opus", 1, 300 + 50 * n)).recording
             for n in (4, 5)]
    st = sets.link(lib, [r.id for r in first], title="Lucía")
    window.model.reload_sets()
    res = watch.ScanResult(imported=[importer.import_file(lib, wav(tmp_path / "PTT-20261023-WA0006.opus", 1, 777))])
    window._watched_import(res)
    assert wait_until(lambda: window.banner.isVisible(), 10)
    assert "seems to continue “Lucía”" in window.banner_text.text() and window.banner_link.text() == "Add to set"
    window.banner_link.click()
    assert len(sets.get(lib, st.id).members) == 3


# ---- found by review: typing must stay where it is, and only edited parts are written ----

def test_typing_stays_in_its_part_while_another_part_changes(window, lib, tmp_path):
    parts = _parts(lib, tmp_path)
    late = importer.import_file(lib, wav(tmp_path / "late.wav", 3, 950)).recording
    late.update(created="2026-10-23T14:01:00-03:00")  # first in the set, not transcribed yet
    late.request_transcription()
    st = sets.link(lib, [late.id, *(r.id for r in parts)])
    window.model.reload_sets()
    window._select(st.id)
    pump(150)
    tp = window.transcript
    ed = tp.editor
    c = ed.textCursor()
    c.setPosition(tp._bodies()[3][0] + 5)  # inside the last part: "Avisa|me"
    ed.setTextCursor(c)
    ed.setFocus()
    QTest.keyClicks(ed, "A")
    # The first part starts transcribing (one rebuild); its progress moving rebuilds nothing.
    late.path("transcribe.progress.json").write_text(json.dumps({"stage": "transcribing", "done": 1, "total": 9}))
    window._refresh()
    shown = tp._shown_signature
    late.path("transcribe.progress.json").write_text(json.dumps({"stage": "transcribing", "done": 5, "total": 9}))
    window._refresh()
    assert tp._shown_signature == shown
    # The first part's transcript arrives (a long line where its state line was): typing continues in place.
    segs = [{"start": 0.0, "end": 2.0, "text": "Un texto bastante más largo que la línea de estado de antes.",
             "paragraph": True}]
    late.path(TRANSCRIPT).write_text(json.dumps({"segments": segs, "text": segs[0]["text"], "language": "es"}))
    late.path("transcribe.progress.json").unlink()
    late.path("transcribe.requested").unlink()
    window._refresh()
    pump(50)
    QTest.keyClicks(ed, "B")
    tp.save()
    assert parts[2].path(EDITED).read_text() == "AvisaABme cuando sepas."
    assert not any(r.path(EDITED).exists() for r in (late, parts[0], parts[1]))


def test_an_input_method_cannot_cross_a_heading_and_unsaved_typing_survives_the_guard(window, lib, tmp_path):
    from PySide6.QtGui import QInputMethodEvent

    _st, parts, _other = _linked(window, lib, tmp_path)
    tp = window.transcript
    ed = tp.editor
    c = ed.textCursor()
    c.setPosition(tp._bodies()[2][1])
    ed.setTextCursor(c)
    ed.setFocus()
    QTest.keyClicks(ed, " abc")  # not saved yet
    before = ed.toPlainText()
    c = ed.textCursor()
    c.setPosition(tp._bodies()[0][0] + 2)
    c.setPosition(tp._bodies()[1][0] + 2, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    ev = QInputMethodEvent()
    ev.setCommitString("é")
    QApplication.sendEvent(ed, ev)
    assert ed.toPlainText() == before
    # Something else gets past the keys anyway: it is undone and the typing is kept.
    c.removeSelectedText()
    assert wait_until(lambda: tp._structure_ok() and ed.toPlainText() == before, 2)
    tp.save()
    assert parts[2].path(EDITED).read_text() == "Avisame cuando sepas. abc"
    assert not parts[0].path(EDITED).exists() and not parts[1].path(EDITED).exists()
    # The fixed blank line between parts is protected the same way.
    sep = ed.document().findBlock(tp._bodies()[1][0] - 1).previous()
    c = QTextCursor(sep)
    c.insertText("x")
    assert wait_until(lambda: tp._structure_ok() and ed.toPlainText() == before, 2)


def test_non_breaking_spaces_do_not_make_a_part_look_edited(window, lib, tmp_path):
    st, parts, _other = _linked(window, lib, tmp_path)
    segs = [{"start": 0.0, "end": 2.0, "text": "Son 10 000 cajas.", "paragraph": True}]
    parts[0].path(TRANSCRIPT).write_text(json.dumps({"segments": segs, "text": segs[0]["text"], "language": "es"}))
    window._refresh()
    pump(50)
    tp = window.transcript
    c = tp.editor.textCursor()
    c.setPosition(tp._bodies()[2][1])
    tp.editor.setTextCursor(c)
    tp.editor.insertPlainText(" Gracias.")
    tp.save()
    assert parts[2].path(EDITED).exists() and not parts[0].path(EDITED).exists()
    # The same for a recording on its own.
    window.model.set_expanded(st.id, True)
    window._select(parts[0].id)
    pump(100)
    window.transcript.save()
    assert not parts[0].path(EDITED).exists()


def test_delete_acts_on_the_highlighted_rows(window, lib, tmp_path):
    from PySide6.QtCore import QItemSelectionModel

    a, b = _parts(lib, tmp_path, 2)
    window.model.refresh()
    sm = window.list.selectionModel()
    window.list.setCurrentIndex(window.model.index(window.model.row_of(a.id)))
    idx_b = window.model.index(window.model.row_of(b.id))
    sm.setCurrentIndex(idx_b, QItemSelectionModel.SelectionFlag.Select)
    sm.setCurrentIndex(idx_b, QItemSelectionModel.SelectionFlag.Deselect)  # Ctrl+click B again
    assert window.current().id == b.id and window._selected_keys() == [a.id]
    asked = []
    QTimer.singleShot(200, lambda: (asked.append(QApplication.activeModalWidget().text()),
                                    QApplication.activeModalWidget().reject()))
    window.delete_selected()
    assert "Nota 1" in asked[0] and lib.get(b.id) is not None

"""Passage times in the window: the margin, follow-along on edited text, copy with timestamps."""

from PySide6.QtWidgets import QApplication

from echo_app import settings
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures


def test_margin_toggle_is_remembered(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    assert not tp.editor.margin.isVisible()
    window.a_times.trigger()
    assert tp.show_timestamps and tp.editor.margin.isVisible() and tp.times_btn.isChecked()
    assert [t for _p, t in tp.editor.margin.stamps] == [0.0, 2.0]
    assert tp.editor.viewportMargins().left() > 0
    tp.editor.margin.grab()  # paints
    assert settings.load()[0].show_timestamps
    tp.times_btn.click()
    assert not tp.show_timestamps and not window.a_times.isChecked() and not tp.editor.margin.isVisible()


def test_edited_text_still_follows_and_seeks(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    rec.save_edited("Hola mundo querido.\n\nLa segunda parte.")
    window._select(rec.id)
    pump(100)
    tp = window.transcript
    assert [(a, b) for a, b, _t in tp._spans] == [(0, 19), (21, 38)]  # "La" after the break joins the second
    tp.follow(2.5)
    assert tp._current_span == 1
    seeks = []
    tp.seek_requested.connect(seeks.append)
    tp._on_ctrl_click(25)
    assert seeks == [2.0]
    # Typing keeps the mapping: a moment later the spans follow the new text.
    tp.editor.moveCursor(tp.editor.textCursor().MoveOperation.Start)
    tp.editor.insertPlainText("Bueno. ")
    assert wait_until(lambda: tp._spans and tp._spans[1][0] == 28, 3)


def test_copy_with_timestamps(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(100)
    window.a_copy_times.trigger()
    assert QApplication.clipboard().text() == "[0:00] Hola mundo.\n\n[0:02] Segunda parte.\n"

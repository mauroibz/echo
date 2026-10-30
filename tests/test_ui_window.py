"""The refined window: menu button, messages, tag filter, date groups, header, Details, speaker names."""

from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeySequence, QMouseEvent

from echo_app.ui import common, library_view
from test_speaker_search import meeting
from test_ui import _transcribed, lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures


def test_menus_live_in_a_button_and_shortcuts_still_work(window):
    from PySide6.QtWidgets import QStatusBar

    assert window.menuWidget() is None and window.findChild(QStatusBar) is None
    menus = [a.text() for a in window.app_menu.actions() if a.menu()]
    assert menus == ["&File", "&Edit", "&View", "&Recording", "&Help"]
    keys = {a.shortcut().toString() for a in window.actions()}
    assert {"Ctrl+R", "Ctrl+O", "Ctrl+E", "Ctrl+I", "Ctrl+Shift+P"} <= keys  # on the window, not only the menu
    assert window.menu_btn.menu() is window.app_menu and window.people_btn.isVisible()


def test_messages_show_and_go(window):
    window.show_message("Imported 3.", 300)
    assert window.toast.isVisible() and window.toast.text() == "Imported 3."
    assert wait_until(lambda: not window.toast.isVisible(), 3)


def test_tag_bar_opens_from_the_filter_and_shows_itself_while_filtering(window, lib):
    rec = lib.create("Entrevista", "imported")
    rec.set_tags(["entrevista"])
    window.model.refresh()
    window._update_tags()
    assert not window.tag_bar.isVisible()
    window.search.setText("#entrevista")
    window._update_tags()
    assert window.tag_bar.isVisible()  # an active filter is never hidden
    window.search.clear()
    window._update_tags()
    assert not window.tag_bar.isVisible()
    window.filter_action.trigger()
    assert window.tag_bar.isVisible()
    window.filter_action.trigger()
    assert not window.tag_bar.isVisible()


def test_date_groups_and_quiet_rows(window, lib, tmp_path):
    now = datetime.now().astimezone()
    rec = _transcribed(lib, tmp_path)
    old = lib.create("Vieja", "imported")
    old.update(created=(now - timedelta(days=400)).isoformat(timespec="seconds"))
    window._refresh()
    m = window.model
    headings = [m.data(m.index(r), library_view.ROLE_HEADER) for r in range(m.rowCount())]
    assert headings[0] == "Today" and headings[-2] and headings[-2].endswith(str((now - timedelta(days=400)).year))
    st = m.data(m.index(m.row_of(rec.id)), library_view.ROLE_STATUS)
    assert st.kind == library_view.K_DONE
    window.list.grab()  # paints a done row with no status, and a heading


def test_list_dates_and_lengths():
    now = datetime.now().astimezone()
    iso = lambda d: (now - timedelta(days=d)).isoformat(timespec="seconds")  # noqa: E731
    assert common.date_group(iso(0)) == "today" and common.date_group(iso(1)) == "yesterday"
    assert common.date_group(iso(40)) == (now - timedelta(days=40)).strftime("%Y-%m")
    if now.weekday() >= 2:  # two days ago is still this week from Wednesday on
        assert common.date_group(iso(2)) == "week"
    assert common.fmt_when(iso(0)) == (now.strftime("%H:%M"))
    assert common.fmt_length(41) == "41 s" and common.fmt_length(1980) == "33 min"
    assert common.fmt_length(5400) == "1 h 30 min" and common.fmt_length(7200) == "2 h"
    assert library_view.group_title("today") == "Today"
    assert library_view.group_title(f"{now.year}-03") == "March"
    assert library_view.group_title("2019-03") == "March 2019"


def test_header_and_details(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    rec.update(notes="Llamar el lunes", markers=[{"at": 1.0, "note": "Clave"}])
    window.model.refresh()
    window._select(rec.id)
    pump(200)
    assert "words" not in window.player.subtitle.text()  # one line: date and length
    assert not window.details.isVisible()
    window.details_btn.click()
    assert window.details.isVisible() and window.a_details.isChecked()
    window.details.refresh()
    shown = {sec.findChildren(type(window.player.subtitle))[0].text(): sec.isVisible()
             for sec, _w, _t in window.details.sections}
    assert shown["NOTES"] and shown["MARKERS"] and shown["STATISTICS"] and shown["TRANSCRIPT"]
    assert window.player.notes.toPlainText() == "Llamar el lunes"
    assert "4 words" in window.player.stats.text()
    seeks = []
    window.details.seek_requested.connect(seeks.append)
    row = window.details.markers.findChildren(type(window.details.markers.layout().itemAt(0).widget()))[0]
    assert "Clave" in row.text()
    row.click()
    assert seeks == [1.0]
    window._save_layout()
    assert window.state.get("details") is True
    window.show_details(False)
    assert not window.details.isVisible() and not window.details_btn.isChecked()


def test_speaker_names_over_turns_open_the_speaker_menu(window, lib):
    rec = meeting(lib, "Weekly", [(1, "El precio sube en enero."), (2, "Y el precio de febrero?")],
                  {1: "Ana", 2: "Pedro"})
    window.model.refresh()
    window._select(rec.id)
    pump(300)
    ed = window.transcript.editor
    assert [name for _p, name, _c, _n in ed.heads] == ["Ana", "Pedro"]
    assert not ed.margin.labels and not ed.margin.isVisible()  # no column of names beside the text
    ed.viewport().grab()
    ed.viewport().repaint()
    assert len(ed._head_rects) == 2
    clicked = []
    ed.speaker_clicked.disconnect()  # not the real menu, which would wait for a choice
    ed.speaker_clicked.connect(lambda n, _pos: clicked.append(n))
    rect, n = ed._head_rects[1]
    ed.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(rect.center()),
                                   QPointF(ed.viewport().mapToGlobal(rect.center())), Qt.MouseButton.LeftButton,
                                   Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert clicked == [2]


def test_recorder_at_rest_and_while_recording(window):
    panel = window.recorder_panel
    assert panel.record_btn.isVisible() and panel.source_btn.isVisible()
    assert not panel.elapsed.isVisible() and not panel.meter.isVisible() and not panel.mark_btn.isVisible()
    assert panel.source_btn.text() == panel.current_source().short_label
    panel.show_inputs()
    assert panel.input_panel.isVisible() and panel.source.isVisible()
    panel.input_panel.hide()
    panel.start()
    assert wait_until(lambda: panel.session is not None)
    assert panel.elapsed.isVisible() and panel.mark_btn.isVisible() and not panel.source_btn.isVisible()
    assert QKeySequence("M") in [a.shortcut() for a in window.actions()]
    panel.stop()
    assert wait_until(lambda: panel.source_btn.isVisible())

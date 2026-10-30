"""Tags, notes, month headings and statistics in the window."""

from datetime import datetime, timedelta

from echo_app.ui import library_view
from echo_app.ui.player import statistics
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures



def _first(window):
    """The recording in the list's first row under its date heading."""
    return window.model.recording(window.model.first_row())

def test_tag_editor_notes_and_chip_filter(window, lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    other = lib.create("Otra", "imported")
    window.model.refresh()
    window._select(rec.id)
    pump(100)
    ed = window.player.tags
    ed.entry.setText("entrevista")
    ed.entry.returnPressed.emit()
    ed.entry.setText("#Trabajo")
    ed.entry.returnPressed.emit()
    assert lib.get(rec.id).meta.tags == ["entrevista", "Trabajo"]
    ed._remove("Trabajo")
    assert lib.get(rec.id).meta.tags == ["entrevista"]
    window.player.notes.setPlainText("Llamar a Ana el lunes")
    window.player.notes.edited.emit("Llamar a Ana el lunes")
    assert lib.get(rec.id).meta.notes == "Llamar a Ana el lunes"
    # The chip bar opens from the filter in the search field, lists the tag, and clicking it
    # filters the list through the search box.
    bar = window.tag_bar
    assert not bar.isVisible()
    window.filter_action.trigger()
    assert bar.isVisible() and bar.flow.count() == 1
    chip = bar.flow.itemAt(0).widget()
    assert chip.text().startswith("#entrevista")
    chip.click()
    assert window.search.text() == "#entrevista"
    assert wait_until(lambda: window.model.shown() == 1 and _first(window).id == rec.id)
    chip = bar.flow.itemAt(0).widget()
    assert chip.isChecked()
    chip.click()
    assert window.search.text() == ""
    assert wait_until(lambda: window.model.row_of(other.id) >= 0)
    # Notes are searchable.
    window.search.setText("lunes")
    assert wait_until(lambda: window.model.shown() == 1)


def test_month_headings_when_the_library_spans_months(window, lib, monkeypatch):
    now = datetime.now().astimezone()
    for months_ago in (0, 0, 1, 3):
        rec = lib.create(f"r{months_ago}", "imported")
        rec.update(created=(now - timedelta(days=31 * months_ago)).isoformat(timespec="seconds"))
    window._refresh()
    m = window.model
    headings = [m.data(m.index(r), library_view.ROLE_HEADER) for r in range(m.rowCount())]
    assert sum(1 for h in headings if h) == 3
    assert headings[0] and not m.flags(m.index(0))  # a heading is not selectable
    assert m.first_row() == 1 and m.recording(1) is not None
    assert window.current() is not None and window.current().meta.title.startswith("r")
    window.list.grab()  # paints headings


def test_statistics(lib, tmp_path):
    rec = _transcribed(lib, tmp_path)
    rec.update(duration=4.0)
    # "Hola mundo. Segunda parte." is 4 words in 3.4 s of passages.
    assert statistics(rec) == "4 words  ·  71 words a minute  ·  15% silence"
    assert statistics(lib.create("x", "imported")) == ""


def test_category_chip_groups_values(window, lib):
    a, b, c = (lib.create(t, "imported") for t in ("Acme call", "Globex call", "Diario"))
    a.set_tags(["client:Acme"])
    b.set_tags(["client:Globex", "client:Acme"])
    c.set_tags(["nota"])
    window.model.refresh()
    window._update_tags()
    bar = window.tag_bar
    chips = [bar.flow.itemAt(i).widget() for i in range(bar.flow.count())]
    assert [ch.text() for ch in chips] == ["client ▾  2", "#nota  1"]  # two recordings, not three tags
    actions = [a.text() for a in chips[0].menu().actions() if a.text()]
    assert actions == ["Any client  (2)", "Acme  (2)", "Globex  (1)"]
    next(x for x in chips[0].menu().actions() if x.text().startswith("Globex")).trigger()
    assert window.search.text() == "#client:Globex"
    assert wait_until(lambda: window.model.shown() == 1 and _first(window).id == b.id)
    chip = bar.flow.itemAt(0).widget()
    assert chip.isChecked()
    next(x for x in chip.menu().actions() if x.text().startswith("Globex")).trigger()
    next(x for x in bar.flow.itemAt(0).widget().menu().actions() if x.text().startswith("Any")).trigger()
    assert window.search.text() == "#client:"
    assert wait_until(lambda: window.model.shown() == 2)
    # The editor sets a category apart, and "client:" completes its values.
    window._select(a.id)
    pump(100)
    ed = window.player.tags
    assert ed._chips[0].text() == "client › Acme  ×"
    ed._completer.setCompletionPrefix("client:")
    assert ed._completer.completionCount() == 2

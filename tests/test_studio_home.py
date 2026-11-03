"""Echo Studio's window: the rail, the home (next meeting, minutes), People by email."""

from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from echo_app import people
from echo_studio import calendar, summary
from test_studio import _attach, keyring, server, studio  # noqa: F401 - fixtures
from test_studio_calendar import _now_feed, feed  # noqa: F401 - fixtures
from test_ui import lib, pump, qapp, wait_until  # noqa: F401 - fixtures
from test_vault import _rec


@pytest.fixture
def swindow(qapp, lib, monkeypatch, studio):
    from echo_app.audio import monitor, pipewire
    from echo_app.ui import common
    from echo_studio import meetings
    from echo_studio.window import StudioWindow

    monkeypatch.setattr(pipewire, "list_sources", lambda: [pipewire.Source("fake", "Test mic", pipewire.INPUT, 1, True)])
    monkeypatch.setattr(monitor.LevelMonitor, "start", lambda self: None)
    monkeypatch.setattr(meetings, "_state_path", lambda: lib.data_dir / "meetings-state.json")
    st = common.UiState()
    st.data = {}
    w = StudioWindow(lib, st)
    w.show()
    pump(200)
    yield w
    if w.recorder_panel.session is not None:
        w.recorder_panel.stop()
        wait_until(lambda: not any(r.meta.state == "recording" for r in lib.all()), 20)
    w._quitting = True
    w.shutdown()
    w.close()
    w.deleteLater()
    pump(50)


def _texts(widget) -> list[str]:
    return [lbl.text() for lbl in widget.findChildren(QLabel)]


def test_echos_window_until_studio_is_set_up(swindow):
    import echo_studio

    assert echo_studio.window_class().__name__ == "StudioWindow"
    _attach(swindow)
    assert not swindow.rail.isVisible() and swindow.pages.currentWidget() is swindow.recordings_page


def test_home_lists_the_minutes_and_opens_them(swindow, lib, server):
    from echo_studio.ui import SummaryView

    rec = _rec(lib)
    rec.update(speakers={"1": "Lucía"})
    summary.finish(rec, summary.write(rec))
    swindow.model.refresh()
    _attach(swindow)
    assert swindow.rail.isVisible() and swindow.page() == "home"
    home = swindow.pages.currentWidget()
    texts = _texts(home)
    assert "Minutes" in texts and rec.meta.title in texts and "ACTION ITEMS · 1" in texts
    assert "Enviar la propuesta" in texts  # the items at a glance
    assert any("Lucía habló del precio." in t for t in texts)  # the minutes' excerpt
    assert "Add your calendar" in [b.text() for b in home.findChildren(QPushButton)]  # no calendar yet
    from echo_studio.home import MinutesCard

    card = next(c for c in home.findChildren(MinutesCard) if c.rid == rec.id)
    from echo_studio import marks

    card.star.click()
    assert marks.starred(lib.get(rec.id)) and swindow.page() == "home"  # the star does not open it
    card.clicked.emit(rec.id)
    assert swindow.page() == "recordings" and swindow.current().id == rec.id
    assert isinstance(swindow.views.stack.currentWidget(), SummaryView)  # opened on its minutes
    from echo_studio.ui import ActionsView

    swindow.show_page("home")
    card = next(c for c in home.findChildren(MinutesCard) if c.rid == rec.id)
    card.items_clicked.emit(rec.id)  # its action items open their own view
    assert swindow.page() == "recordings" and isinstance(swindow.views.stack.currentWidget(), ActionsView)
    swindow.show_page("home")
    swindow.show_recording(rec.id)  # anything that shows a recording goes to Recordings
    assert swindow.page() == "recordings"


def test_home_shows_the_next_meeting(swindow, lib, feed, monkeypatch):
    import echo_studio

    now = datetime.now().astimezone().replace(microsecond=0)
    feed.text = _now_feed(now + timedelta(minutes=25))
    calendar.save_urls(feed.url)
    _attach(swindow)
    assert swindow.rail.isVisible()  # a calendar alone is enough
    home = swindow.pages.currentWidget()
    assert wait_until(lambda: "Roadmap review" in _texts(home), 5)
    texts = _texts(home)
    assert any(t.endswith("UP NEXT IN 25 MIN") or t.endswith("UP NEXT IN 24 MIN") for t in texts)
    start = (now + timedelta(minutes=25)).strftime("%H:%M")
    assert start in texts and f"●  Records by itself at {start}" in texts
    buttons = {b.text(): b for b in home.findChildren(QPushButton)}
    assert "Join the call  →" in buttons
    buttons["Don't record"].click()
    assert wait_until(lambda: "Not recording this one" in _texts(home))
    assert echo_studio._meetings.is_skipped(echo_studio._meetings.next_event())
    assert "Record now" not in [b.text() for b in home.findChildren(QPushButton)]  # the rail's Record does that
    {b.text(): b for b in home.findChildren(QPushButton)}["Record it"].click()
    assert wait_until(lambda: any(t.startswith("●  Records by itself") for t in _texts(home)))
    # Coming up: the same meeting with its switch, and one without a link, off until turned on.
    from echo_studio.widgets import Toggle

    assert "Coming up" in _texts(home)
    [sw] = home.coming.findChildren(Toggle)
    assert sw.isChecked() and "Roadmap review" in sw.toolTip()
    sw.click()
    assert wait_until(lambda: echo_studio._meetings.is_skipped(echo_studio._meetings.next_event()))
    assert "Not recording this one" in _texts(home)


def test_record_heads_the_rail(swindow, lib, server):
    _attach(swindow)
    lay = swindow.rail.lay
    assert lay.itemAt(0).widget() is swindow.rail_record  # above Briefing, Recordings and People
    assert swindow.rail.top.itemAt(0).widget().toolTip().startswith("Briefing")
    assert swindow.page() == "home" and not swindow.rail.clock.isVisible()
    swindow.rail_record.click()
    assert wait_until(lambda: swindow.recording_id() is not None)
    assert swindow.page() == "home"  # recorded from where the user is
    assert wait_until(lambda: swindow.rail.clock.isVisible() and swindow.rail.clock.text() == "0:01", 5)
    assert swindow.rail_record.accessibleName() == "Stop recording"
    swindow.show_page("people")
    swindow.rail_record.click()  # stops from any page
    assert wait_until(lambda: swindow.recording_id() is None)
    assert not swindow.rail.clock.isVisible() and swindow.rail_record.accessibleName() == "Record"


def test_home_while_recording(swindow, lib, feed):
    now = datetime.now().astimezone().replace(microsecond=0)
    feed.text = _now_feed(now + timedelta(hours=3))
    calendar.save_urls(feed.url)
    _attach(swindow)
    home = swindow.pages.currentWidget()
    swindow.rail_record.click()
    assert wait_until(lambda: swindow.recording_id() is not None)
    assert wait_until(lambda: any(t.startswith("RECORDING · SINCE") for t in _texts(home)), 5)
    assert home.hero.live and swindow.rail_record.property("live") in (True, "true")
    home.notes.setPlainText("Precios: confirmar el plan anual")
    pump(1200)
    stop = next(b for b in home.findChildren(QPushButton) if b.text() == "Stop recording")
    rid = swindow.recording_id()
    stop.click()
    assert wait_until(lambda: swindow.recording_id() is None)
    assert lib.get(rid).meta.notes == "Precios: confirmar el plan anual"  # the notes were kept
    assert wait_until(lambda: not home.hero.live, 5)


def test_people_by_email(swindow, lib, server):
    from echo_studio import actions, parts

    rec = _rec(lib)
    rec.update(speakers={"1": "Lucía", "2": "Pedro"})
    summary.finish(rec, summary.write(rec))
    actions.add(rec, "Reservar sala", owner="Lucía")
    people.save(lib, people.Profile("Lucía", email="lucia@acme.example"))
    swindow.model.refresh()
    _attach(swindow)
    swindow.open_people("Lucía")  # from a speaker's name: Studio's page
    assert swindow.page() == "people"
    screen = swindow.pages.currentWidget()
    page = screen.page
    assert page.name == "Lucía"
    texts = _texts(page)
    assert "lucia@acme.example" in texts and "MEETINGS" in texts
    assert "THEIR PART" in texts and parts.part_of(rec, "Lucía") in texts
    assert "•  Propuso subir el precio un 10 %." in texts  # and the points that make it up
    assert "Reservar sala" in texts
    # Their meetings: starred and tagged here, then filtered.
    from echo_app.ui.tags import TagEditor
    from echo_studio import marks
    from echo_studio.home import MinutesCard

    [card] = page.findChildren(MinutesCard)
    card.star.click()
    assert marks.starred(lib.get(rec.id))
    ed = card.findChild(TagEditor)
    ed.entry.setText("precios")
    ed.entry.returnPressed.emit()
    assert "precios" in lib.get(rec.id).meta.tags
    screen.reload()
    page = screen.page
    chips = {b.text(): b for b in page.findChildren(QPushButton) if b.objectName() == "filterChip"}
    assert {"All  1", "★ Starred  1", "#precios"} <= set(chips)
    lib.get(rec.id).update(tags=[])
    page.meetings[0]["tags"] = []
    chips["#precios"].click()
    assert "No meetings with them match." in _texts(page)
    chips["★ Starred  1"].click()
    assert len(page.findChildren(MinutesCard)) == 1
    # Their items are polished here too.
    from PySide6.QtWidgets import QToolButton

    next(b for b in page.findChildren(QToolButton) if b.accessibleName() == "Discard").click()
    assert sum(i["discarded"] for i in actions.load(lib.get(rec.id))["items"]) == 1
    assert page.stats["ACTION ITEMS"].text() == "1"
    page.email.setText("pedro@acme.example")
    people.save(lib, people.Profile("Pedro", email="pedro@acme.example"))
    from PySide6.QtWidgets import QMessageBox

    shown = []
    import echo_studio.people_ui as pui

    pui.QMessageBox.information = staticmethod(lambda *a: shown.append(a[2]) or QMessageBox.StandardButton.Ok)
    page.email.editingFinished.emit()
    assert shown and "Pedro" in shown[0] and people.load(lib, "Lucía").email == "lucia@acme.example"
    page.notes.setPlainText("Lidera producto")
    screen.list.setCurrentRow(1)
    assert people.load(lib, "Lucía").notes == "Lidera producto"
    screen.reload()
    screen.filter.setText("acme")  # by email too
    assert screen.list.count() == 2

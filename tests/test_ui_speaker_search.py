"""Searching by speaker in the window: snippets, finding in their passages, and @ completion."""

from echo_app.ui.library_view import ROLE_SNIPPET
from test_speaker_search import meeting
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures



def _first(window):
    """The recording in the list's first row under its date heading."""
    return window.model.recording(window.model.first_row())

def test_what_ana_said_about_the_price(window, lib):
    a = meeting(lib, "Weekly", [(1, "El precio sube en enero."), (2, "Y el precio de febrero?")],
                {1: "Ana López", 2: "Pedro"})
    meeting(lib, "Globex", [(1, "Hablemos del precio."), (2, "Bien.")], {1: "Pedro", 2: "Ana López"})
    window.model.refresh()
    window.search.setText("@ana precio")
    assert wait_until(lambda: window.model.shown() == 1 and _first(window).id == a.id)
    snippet = window.model.data(window.model.index(window.model.first_row()), ROLE_SNIPPET)
    assert snippet.startswith("Ana López: El precio sube")
    window.list.grab()  # paints the third line
    window._select(a.id)
    pump(200)
    tp = window.transcript
    assert wait_until(lambda: tp.findbar.isVisible() and tp._find_matches)
    assert len(tp._find_matches) == 1 and tp._speaker_at(tp._find_matches[0][0]) == 1  # not Pedro's "precio"
    tp.find_edit.setText("precio")
    tp.find_edit.textEdited.emit("precio")  # typed in the find bar: everyone's words again
    assert len(tp._find_matches) == 2
    window.search.setText("precio")
    assert wait_until(lambda: window.model.shown() == 2)
    assert window.model.data(window.model.index(window.model.first_row()), ROLE_SNIPPET) is None


def test_at_offers_the_people_who_speak(window, lib):
    meeting(lib, "Weekly", [(1, "Hola."), (2, "Chau.")], {1: "Ana López", 2: "Pedro"})
    window.model.refresh()
    window.search.setText("#client:acme @an")
    window.search.setCursorPosition(len(window.search.text()))
    window._offer_people(window.search.text())
    assert window._people.completionCount() == 1 and window._people.currentCompletion() == "Ana_López"
    window._complete_person("Ana_López")
    assert window.search.text() == "#client:acme @Ana_López "

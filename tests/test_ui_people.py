"""The People window: the list, a profile's notes, tags, aliases, recordings and voice."""

from echo_app import dictionary, people
from test_speaker_search import meeting
from test_ui import lib, pump, qapp, wait_until, window  # noqa: F401 - fixtures


def _two_meetings(lib):
    a = meeting(lib, "Weekly", [(1, "Hola."), (2, "Chau.")], {1: "Ana López", 2: "Pedro"})
    b = meeting(lib, "Globex", [(1, "Hola."), (2, "Un rato largo."), (2, "x")], {1: "Pedro", 2: "Ana López"})
    a.update(created="2026-10-01T10:00:00-03:00")
    b.update(created="2026-10-20T10:00:00-03:00")
    return a, b


def test_profile_keeps_notes_tags_and_aliases(window, lib):
    a, b = _two_meetings(lib)
    window.model.refresh()
    window.open_people("ana lopez")
    dlg = window._people_dialog
    assert dlg.isVisible() and dlg.name_label.text() == "Ana López"
    assert dlg.summary.text().startswith("Speaks in 2 recordings")
    assert [dlg.recordings.item(i).text().split("   ")[0] for i in range(2)] == ["Globex", "Weekly"]  # newest first
    dlg.notes.setPlainText("CFO de Acme")
    dlg.tags.changed.emit(["client:Acme"])
    dlg.aliases.setText("Anita, Ani")
    dlg.aliases.editingFinished.emit()
    dlg.email.setText("Ana <ANA@acme.example>")
    dlg.email.editingFinished.emit()
    assert dlg.email.text() == "ana@acme.example" and people.load(lib, "Ana López").email == "ana@acme.example"
    dlg.email.setText("no")
    dlg.email.editingFinished.emit()
    assert dlg.email.text() == "ana@acme.example"  # not an address: the saved one stays
    dlg.list.setCurrentRow(1)  # another person: the notes are saved on the way
    prof = people.load(lib, "Ana López")
    assert prof.notes == "CFO de Acme" and prof.tags == ["client:Acme"]
    assert dictionary.current().find("Ana López").aliases == ["Anita", "Ani"]
    dlg.filter.setText("ped")
    assert dlg.list.count() == 1 and dlg.name_label.text() == "Pedro"
    dlg.close()
    window._people_dialog = None
    window.open_people("Ana López")  # a new window reads it all back
    dlg = window._people_dialog
    assert dlg.notes.toPlainText() == "CFO de Acme" and dlg.tags.tags == ["client:Acme"]
    assert dlg.aliases.text() == "Anita, Ani"
    dlg.close()


def test_open_a_recording_hear_the_voice_and_forget_it(window, lib, monkeypatch):
    a, b = _two_meetings(lib)
    b.update(audio="audio.flac")
    dictionary.remember_voice("Ana López", [1.0, 0.0])
    window.model.refresh()
    window.open_people("Ana López")
    dlg = window._people_dialog
    played = []
    monkeypatch.setattr(dlg._playback, "load", lambda *a: None)
    monkeypatch.setattr(dlg._playback, "play", lambda s, e: played.append((s, e)))
    dlg.play.click()
    assert played == [(2.0, 3.5)]  # her longest passage in her latest recording (Globex)
    assert dlg.forget.isEnabled()
    dlg.forget.click()
    assert "Ana López" not in dictionary.voices() and not dlg.forget.isEnabled()
    dlg.recordings.itemActivated.emit(dlg.recordings.item(1))
    assert wait_until(lambda: window.current() is not None and window.current().id == a.id)
    dlg.close()


def test_profile_from_a_speaker_name(window, lib):
    a, _b = _two_meetings(lib)
    window.model.refresh()
    window._select(a.id)
    pump(200)
    window.transcript.profile_requested.emit("Pedro")
    assert window._people_dialog.name_label.text() == "Pedro"
    window._people_dialog.close()

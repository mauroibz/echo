"""The naming bar: one unnamed speaker at a time over the transcript, and Echo learning the user."""

import json

from PySide6.QtWidgets import QApplication

from echo_app import dictionary, settings
from test_speakers import _with_speakers
from test_ui import lib, pump, qapp, window  # noqa: F401 - fixtures


def _show(window, lib, tmp_path, suggested=None):
    rec = _with_speakers(lib, tmp_path)  # speaker 1 speaks 1.5 s, speaker 2 1.9 s
    if suggested:
        t = json.loads(rec.path("transcript.json").read_text())
        t["speakers"]["suggested"] = suggested
        rec.path("transcript.json").write_text(json.dumps(t))
    window._select(rec.id)
    pump(200)
    return rec, window.transcript


def test_asks_most_speech_first_then_the_next_then_learns_the_user(window, lib, tmp_path):
    rec, tp = _show(window, lib, tmp_path)
    assert tp.namebar.isVisible() and tp.name_text.text() == "Who is speaker 2?"
    assert tp.name_edit.isVisible() and tp.name_me.isVisible() and not tp.name_yes.isVisible()
    tp.name_edit.setText("Pedro")
    tp.name_edit.returnPressed.emit()
    pump(50)
    assert lib.get(rec.id).meta.speakers == {"2": "Pedro"}
    assert tp.name_text.text() == "Who is speaker 1?"
    tp.name_me.click()  # Echo does not know the user's name yet: it asks, inline
    assert "your name" in tp.name_text.text() and tp.name_edit.isVisible() and not tp.name_me.isVisible()
    tp.name_edit.setText("Sofía")
    tp.name_edit.returnPressed.emit()
    pump(50)
    assert settings.load()[0].your_name == "Sofía"
    assert lib.get(rec.id).meta.speakers == {"1": "Sofía", "2": "Pedro"}
    assert "Sofía" in dictionary.voices() and not tp.namebar.isVisible()


def test_known_voice_in_one_click_or_someone_else(window, lib, tmp_path):
    rec, tp = _show(window, lib, tmp_path, suggested={"2": "Ana"})
    assert tp.name_text.text() == "Speaker 2 sounds like <b>Ana</b>."
    assert tp.name_yes.isVisible() and tp.name_yes.text() == "Yes, Ana" and not tp.name_edit.isVisible()
    tp.name_other.click()
    assert tp.name_edit.isVisible() and not tp.name_yes.isVisible()
    tp.name_edit.setText("Lucía")
    tp.name_edit.returnPressed.emit()
    pump(50)
    assert lib.get(rec.id).meta.speakers == {"2": "Lucía"}
    tp.name_speaker(2, "")  # "Forget this name" in the margin: the bar asks again
    tp.name_yes.click()
    assert lib.get(rec.id).meta.speakers == {"2": "Ana"}


def test_its_me_when_the_name_is_known_and_never_asked_again(window, lib, tmp_path):
    settings.save(settings.Settings(auto_transcribe=False, your_name="Sofía"))
    rec, tp = _show(window, lib, tmp_path)
    tp.name_me.click()
    assert lib.get(rec.id).meta.speakers == {"2": "Sofía"}
    assert tp.name_text.text() == "Who is speaker 1?" and not tp.name_me.isVisible()  # one of them is you


def test_not_now_is_for_good(window, lib, tmp_path):
    rec, tp = _show(window, lib, tmp_path)
    tp.name_skip.click()
    assert not tp.namebar.isVisible() and lib.get(rec.id).meta.naming_dismissed
    window._select(None)
    pump(50)
    window._select(rec.id)
    pump(200)
    assert not tp.namebar.isVisible()


def test_hear_the_speaker(window, lib, tmp_path, monkeypatch):
    rec, tp = _show(window, lib, tmp_path)
    played = []
    monkeypatch.setattr(tp.player, "play_span", lambda a, b: played.append((a, b)))
    tp.name_play.click()
    assert played == [(2.0, 3.9)]  # speaker 2's longest passage, under 6 s so all of it


def test_waits_for_the_dictionary_chip_and_takes_no_focus(window, lib, tmp_path):
    rec, tp = _show(window, lib, tmp_path)
    tp.editor.setFocus()
    pump(50)
    tp.refresh()
    pump(50)
    assert tp.namebar.isVisible() and QApplication.focusWidget() is tp.editor
    tp.chip.show()
    tp._update_namebar()
    assert not tp.namebar.isVisible()
    tp.chip.hide()
    tp._update_namebar()
    assert tp.namebar.isVisible()


def test_gone_when_everyone_is_named_or_labels_are_off(window, lib, tmp_path):
    rec, tp = _show(window, lib, tmp_path)
    tp.set_speakers_off(True)
    assert not tp.namebar.isVisible()
    tp.set_speakers_off(False)
    assert tp.namebar.isVisible()
    tp.name_speaker(1, "Ana")
    tp.name_speaker(2, "Pedro")
    assert not tp.namebar.isVisible()


def test_your_name_in_settings_keeps_the_voice(qapp):
    from echo_app.ui.dialogs import SettingsDialog

    settings.save(settings.Settings(your_name="Sofía"))
    dictionary.remember_voice("Sofía", [1.0, 0.0])
    d = SettingsDialog(recording_active=False)
    assert d.your_name.text() == "Sofía"
    d.your_name.setText("Sofía Paz ")
    d.accept()
    assert settings.load()[0].your_name == "Sofía Paz"
    assert list(dictionary.voices()) == ["Sofía Paz"]
    d.deleteLater()

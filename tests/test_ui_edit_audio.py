"""Editing with the audio: play the passage at the cursor, step through passages, pause while typing."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from echo_app.audio.playback import Playback
from test_ui import _transcribed, lib, pump, qapp, wait_until, wav, window  # noqa: F401 - fixtures


@pytest.fixture
def plays(monkeypatch):
    """Playback without pw-play: records (start, end) and pretends to play until paused."""
    calls = []

    def play(self, start=None, end=None):
        calls.append((start, end))
        self._pos = start or 0.0
        self._end = end
        self._out = object()  # "playing"

    def pause(self):
        self._out = None

    monkeypatch.setattr(Playback, "play", play)
    monkeypatch.setattr(Playback, "pause", pause)
    monkeypatch.setattr(Playback, "poll", lambda self: False)
    return calls


def _type(editor, text):
    for ch in text:
        editor.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))


def test_play_the_passage_at_the_cursor_and_step(window, lib, tmp_path, plays):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    c = tp.editor.textCursor()
    c.setPosition(16)  # inside "Segunda parte."
    tp.editor.setTextCursor(c)
    tp.play_passage()
    assert plays[-1] == (2.0, 3.9)
    tp.play_passage()  # again: stop
    assert not window.player.is_playing()
    tp.step_passage(-1)
    assert plays[-1] == (0.0, 1.5) and tp.editor.textCursor().position() == 0
    tp.step_passage(1)
    assert plays[-1] == (2.0, 3.9) and tp.editor.textCursor().position() == 13


def test_typing_pauses_and_the_passage_plays_again(window, lib, tmp_path, plays):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    tp._replay.setInterval(200)
    tp.play_passage()
    assert plays == [(0.0, 1.5)] and window.player.is_playing()
    _type(tp.editor, "Ho")
    assert not window.player.is_playing() and tp._typing_paused
    assert wait_until(lambda: len(plays) == 2, 3)
    assert plays[-1] == (0.0, 1.5)  # from the start of the passage
    assert wait_until(lambda: rec.path("transcript.edited.txt").exists(), 3)  # the edit autosaved meanwhile


def test_typing_does_nothing_without_a_passage_playing(window, lib, tmp_path, plays):
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(200)
    _type(window.transcript.editor, "x")
    pump(300)
    assert plays == []


def test_autopause_can_be_turned_off(window, lib, tmp_path, plays):
    from echo_app import settings

    cfg, _ = settings.load()
    cfg.edit_autopause = False
    settings.save(cfg)
    rec = _transcribed(lib, tmp_path)
    window._select(rec.id)
    pump(200)
    tp = window.transcript
    tp.play_passage()
    _type(tp.editor, "x")
    assert window.player.is_playing()


def test_next_passage_to_check(window, lib, tmp_path, plays):
    rec = _transcribed(lib, tmp_path)
    t = json.loads(rec.path("transcript.json").read_text())
    t["segments"][1]["flags"] = ["low"]
    rec.path("transcript.json").write_text(json.dumps(t))
    window._select(rec.id)
    pump(200)
    window.transcript.play_next_flagged()
    assert plays[-1] == (2.0, 3.9)

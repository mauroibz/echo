"""Playback volume: the ffmpeg filter chain, a boost that never clips, and a volume per recording."""

import subprocess
import time

import numpy as np
import pytest

from echo_app import importer, sets
from echo_app.audio import playback
from echo_app.audio.playback import Playback, SetPlayback
from test_ui import lib, pump, qapp, wav, window  # noqa: F401 - fixtures
from test_ui_edit_audio import plays  # noqa: F401 - fixture


def test_filter_chain():
    assert playback._filters(1.0) == []
    assert playback._filters(1.0, 0.5) == ["-af", "volume=0.50"]  # no limiter at or below 100%
    assert playback._filters(1.5, 3.0) == ["-af", f"atempo=1.500,volume=3.00,{playback.LIMITER}"]


def _decode(path, volume):
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-vn", *playback._filters(1.0, volume),
           "-f", "s16le", "-ac", "2", "-ar", str(playback.RATE), "pipe:1"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.int16)


def test_boost_is_louder_and_never_clips(tmp_path):
    src = tmp_path / "speech.wav"
    # Quiet tone with a loud burst in the middle, like a laugh in a quiet meeting.
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='if(between(t,1.4,1.6),0.9,0.08)*sin(2*PI*300*t)':d=3", str(src)], check=True)
    plain, boosted = _decode(src, 1.0), _decode(src, 4.0)
    assert len(boosted) == len(plain)  # same timing: positions stay right
    quiet = slice(0, len(plain) // 3)
    ratio = np.abs(boosted[quiet].astype(float)).mean() / np.abs(plain[quiet].astype(float)).mean()
    assert 3.6 < ratio < 4.2
    assert np.abs(boosted.astype(int)).max() < 32767  # the burst was limited, not clipped
    unlimited = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(src), "-af", "volume=4",
                                "-f", "s16le", "-ac", "2", "-ar", "48000", "pipe:1"], capture_output=True).stdout
    assert (np.abs(np.frombuffer(unlimited, dtype=np.int16).astype(int)) >= 32767).sum() > 1000


def test_set_volume_continues_from_the_same_place(plays):  # noqa: F811
    pb = Playback()
    pb.load("x.wav", 60.0)
    pb.set_volume(2.0)
    assert plays == [] and pb.volume == 2.0  # not playing: nothing starts
    pb.play(12.0)
    pb._t0 = time.monotonic()  # the stand-in play leaves the clock unset
    pb.set_volume(3.0)
    assert plays[-1][0] == pytest.approx(12.0, abs=0.2) and pb.volume == 3.0
    pb.set_volume(9.0)
    assert pb.volume == playback.MAX_VOLUME
    s = SetPlayback()
    s.set_volume(1.5)
    assert s.volume == 1.5 and s.inner.volume == 1.5


def test_volume_per_recording_and_restored(window, lib, tmp_path, plays):  # noqa: F811
    quiet = importer.import_file(lib, wav(tmp_path / "reunion.wav", 2, 300)).recording
    note = importer.import_file(lib, wav(tmp_path / "nota.wav", 2, 500)).recording
    p = window.player
    window._select(quiet.id)
    pump(100)
    assert p.volume.isEnabled() and p.volume.value() == 100
    p.toggle_play()
    p.volume.setValue(300)
    assert p.volume_label.text() == "300%" and p.player.volume == 1.0  # applied once the slider settles
    pump(300)
    assert p.player.volume == 3.0 and p.player.playing and len(plays) == 2  # restarted, still playing
    window._select(note.id)
    pump(100)
    assert p.volume.value() == 100 and p.player.volume == 1.0
    window._select(quiet.id)
    pump(100)
    assert p.volume.value() == 300 and p.player.volume == 3.0
    window._save_state()
    assert window.state.get("volumes") == {quiet.id: 3.0}  # only what differs from 100%
    p.volumes = {}
    window._restore()
    assert p.volumes == {quiet.id: 3.0}
    p.volume_label.click()  # back to 100%
    pump(300)
    assert p.player.volume == 1.0 and p.volumes == {}


def test_linked_set_has_one_volume(window, lib, tmp_path, plays):  # noqa: F811
    parts = [importer.import_file(lib, wav(tmp_path / f"parte{k}.wav", 2, 300 + 100 * k)).recording
             for k in range(2)]
    other = importer.import_file(lib, wav(tmp_path / "otra.wav", 2, 700)).recording
    st = sets.link(lib, [r.id for r in parts], title="Reunión")
    window.model.reload_sets()
    window._select(st.id)
    pump(150)
    p = window.player
    assert p.linked is not None and p.volume.isEnabled()
    p.volume.setValue(250)
    pump(300)
    assert p.player is p._set_player and p.player.volume == 2.5 and p.volumes == {st.id: 2.5}
    window._select(other.id)
    pump(150)
    assert p.player is p._rec_player and p.player.volume == 1.0

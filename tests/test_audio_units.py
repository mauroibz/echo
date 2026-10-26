import math
import struct

from echo_app.audio import levels, pipewire


def node(nid, cls, name, desc, ch=2):
    return {"id": nid, "type": "PipeWire:Interface:Node",
            "info": {"props": {"media.class": cls, "node.name": name, "node.description": desc,
                               "audio.channels": ch}}}


DUMP = [
    {"id": 1, "type": "PipeWire:Interface:Metadata", "props": {"metadata.name": "default"},
     "metadata": [{"key": "default.audio.source", "value": {"name": "usb_mic"}},
                  {"key": "default.audio.sink", "value": {"name": "speakers"}}]},
    node(2, "Audio/Source", "webcam", "Webcam Mic"),
    node(3, "Audio/Source", "usb_mic", "USB Mic"),
    node(4, "Audio/Source/Virtual", "ee_source", "Easy Effects Source"),
    node(5, "Audio/Sink", "hdmi", "HDMI"),
    node(6, "Audio/Sink", "speakers", "Speakers"),
    node(7, "Stream/Input/Audio", "firefox", "Firefox"),
    node(8, "Video/Source", "cam", "Camera"),
]


def test_parse_sources_groups_and_defaults():
    srcs = pipewire.parse_sources(DUMP)
    assert [s.name for s in srcs] == ["usb_mic", "ee_source", "webcam", "speakers", "hdmi"]
    assert srcs[0].is_default and srcs[0].kind == pipewire.INPUT
    assert srcs[3].kind == pipewire.MONITOR and srcs[3].label == "Computer audio: Speakers"
    assert pipewire.default_source(srcs).name == "usb_mic"


def test_resolve_missing_source_falls_back_with_note():
    srcs = pipewire.parse_sources(DUMP)
    s, note = pipewire.resolve("unplugged_mic", srcs)
    assert s.name == "usb_mic" and "not available" in note
    s, note = pipewire.resolve("webcam", srcs)
    assert s.name == "webcam" and note is None


def test_monitor_capture_sets_capture_sink():
    srcs = pipewire.parse_sources(DUMP)
    mon = next(s for s in srcs if s.kind == pipewire.MONITOR)
    cmd = pipewire.record_cmd(mon, 48000, 1, "/x.raw")
    props = cmd[cmd.index("-P") + 1]
    assert "stream.capture.sink=true" in props and cmd[-1] == "/x.raw"
    assert "stream.capture.sink" not in pipewire.record_cmd(srcs[0], 48000, 1, "/x.raw")[4]


def pcm(values):
    return struct.pack(f"<{len(values)}h", *values)


def test_peak_levels():
    assert levels.peak(b"") == (levels.SILENCE_DB, False)
    assert levels.peak(pcm([0] * 100)) == (levels.SILENCE_DB, False)
    db, clip = levels.peak(pcm([0, 16384, -100]))
    assert math.isclose(db, -6.02, abs_tol=0.01) and not clip
    assert levels.peak(pcm([-32768, 0]))[1] is True


def test_tail_peak_reads_only_the_end(tmp_path):
    f = tmp_path / "t.raw"
    f.write_bytes(pcm([32000] * 48000) + pcm([100] * 2400) + b"\x01")  # loud, then quiet tail, odd byte
    db, clip = levels.tail_peak(f, 48000, 1, 0.05)
    assert db < -40 and not clip


def test_default_output_capture_has_no_target():
    """The computer-audio track follows the default output: no --target, so WirePlumber links and moves it."""
    cmd = pipewire.record_cmd(pipewire.DEFAULT_OUTPUT, 48000, 1, "/x.raw")
    assert "--target" not in cmd
    assert "stream.capture.sink=true" in cmd[cmd.index("-P") + 1]
    assert pipewire.DEFAULT_OUTPUT.kind == pipewire.MONITOR

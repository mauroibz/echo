"""Which audio backend Echo picks, and what doctor says about it."""

from echo_app import doctor
from echo_app.audio import backend, pipewire


def _reset(monkeypatch):
    monkeypatch.setattr(backend, "_backend", None)
    monkeypatch.delenv("ECHO_CAPTURE_CMD", raising=False)


def test_pipewire_when_it_runs_audio(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.delenv("ECHO_AUDIO_BACKEND", raising=False)
    monkeypatch.setattr(backend.shutil, "which", lambda c: "/usr/bin/" + c)
    monkeypatch.setattr(pipewire, "list_sources", lambda: [pipewire.Source("m", "Mic", pipewire.INPUT, 1, True)])
    assert backend.choose() == "pipewire" and backend.get().name == "pipewire"


def test_portaudio_when_pipewire_has_no_audio(monkeypatch):
    """Ubuntu 22.04: pw-record is there but PipeWire only does video; PulseAudio has the sound."""
    _reset(monkeypatch)
    monkeypatch.delenv("ECHO_AUDIO_BACKEND", raising=False)
    monkeypatch.setattr(backend.shutil, "which", lambda c: "/usr/bin/" + c)
    monkeypatch.setattr(pipewire, "list_sources", lambda: [])
    assert backend.choose() == "portaudio"
    from echo_app.audio import portaudio

    if portaudio.available():
        b = backend.get()
        assert b.name == "portaudio" and not b.records_outputs and not b.can_listen


def test_forced_backend(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("ECHO_AUDIO_BACKEND", "portaudio")
    assert backend.choose() == "portaudio"


def test_portaudio_source_names_are_prefixed(monkeypatch):
    from echo_app.audio import portaudio

    if not portaudio.available():
        return
    for s in portaudio.PortAudioBackend().list_sources():
        assert s.name.startswith("pa:") and s.kind == pipewire.INPUT
    b = portaudio.PortAudioBackend()
    src, note = b.resolve("alsa_input.some-pipewire-node")  # a saved PipeWire choice is not misread
    assert note and (src is None or src.name.startswith("pa:"))


def test_doctor_reports_the_backend(monkeypatch):
    class Fake:
        name = "portaudio"

        def list_sources(self):
            return [pipewire.Source("pa:ALSA:mic", "mic", pipewire.INPUT, 1, True)]

    monkeypatch.setattr(backend, "choose", lambda: "portaudio")
    monkeypatch.setattr(backend, "get", lambda: Fake())
    c = doctor.check_audio_backend()
    assert "PortAudio, 1 input" in c.detail
    monkeypatch.setattr(backend, "choose", lambda: "pipewire")
    assert doctor.check_audio_backend().status == doctor.OK

import argparse
import shutil

from echo_app import doctor


def _fake_which(missing):
    real = shutil.which

    def which(cmd, *a, **k):
        return None if cmd in missing else real(cmd, *a, **k)

    return which


def test_missing_ffmpeg_fails_with_fix(monkeypatch):
    monkeypatch.setattr(doctor, "_which", _fake_which({"ffmpeg"}))
    monkeypatch.setattr(doctor, "distro", lambda: doctor.FEDORA)
    checks = doctor.check_ffmpeg()
    assert checks[0].status == doctor.FAIL and "dnf install ffmpeg-free" in checks[0].fix
    monkeypatch.setattr(doctor, "distro", lambda: doctor.DEBIAN)
    assert doctor.check_ffmpeg()[0].fix == "sudo apt install ffmpeg"


def test_missing_pipewire_fails(monkeypatch):
    monkeypatch.setattr(doctor, "_which", _fake_which({"pw-record"}))
    monkeypatch.setattr(doctor, "distro", lambda: doctor.FEDORA)
    c = doctor.check_pipewire()
    assert c.status == doctor.FAIL and c.fix == "sudo dnf install pipewire-utils"
    monkeypatch.setattr(doctor, "distro", lambda: doctor.ARCH)
    assert doctor.check_pipewire().fix == "sudo pacman -S pipewire"


OS_RELEASES = {
    'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=44\n': doctor.FEDORA,
    'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n': doctor.DEBIAN,
    'NAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\n': doctor.DEBIAN,
    'NAME="Pop!_OS"\nID=pop\nID_LIKE="ubuntu debian"\n': doctor.DEBIAN,
    "ID=debian\n": doctor.DEBIAN,
    'NAME="Nobara Linux"\nID=nobara\nID_LIKE="rhel centos fedora"\n': doctor.FEDORA,
    "ID=bazzite\nID_LIKE=fedora\n": doctor.FEDORA,
    "ID=manjaro\nID_LIKE=arch\n": doctor.ARCH,
    "ID=endeavouros\nID_LIKE=arch\n": doctor.ARCH,
    "ID=arch\n": doctor.ARCH,
    "ID=opensuse-tumbleweed\nID_LIKE=\"opensuse suse\"\n": doctor.OTHER,
    "": doctor.OTHER,
}


def test_distribution_family_from_os_release():
    for text, family in OS_RELEASES.items():
        assert doctor.parse_os_release(text) == family, text


def test_pkg_cmd_per_family():
    pk = {"fedora": "a-utils", "debian": "a-bin", "arch": "a"}
    assert doctor.pkg_cmd(pk, doctor.FEDORA) == "sudo dnf install a-utils"
    assert doctor.pkg_cmd(pk, doctor.DEBIAN) == "sudo apt install a-bin"
    assert doctor.pkg_cmd(pk, doctor.ARCH) == "sudo pacman -S a"
    other = doctor.pkg_cmd(pk, doctor.OTHER)
    assert "package manager" in other and "a-bin" in other


def _node(cls):
    return {"type": "PipeWire:Interface:Node", "info": {"props": {"media.class": cls, "node.name": "n"}}}


def test_audio_nodes_check():
    # A PipeWire that runs only for video/screen sharing, as on Ubuntu 22.04: no audio nodes.
    empty = [{"type": "PipeWire:Interface:Core"}, _node("Video/Source")]
    c = doctor.check_audio_nodes(empty, doctor.DEBIAN)
    assert c.status == doctor.FAIL and "PulseAudio" in c.detail
    assert "apt install" in c.fix and "22.10" in c.fix
    c = doctor.check_audio_nodes([_node("Audio/Sink"), _node("Audio/Source")], doctor.DEBIAN)
    assert c.status == doctor.OK
    assert "22.10" not in doctor.check_audio_nodes(empty, doctor.FEDORA).fix


def test_display_check_only_on_x11(monkeypatch):
    monkeypatch.setattr(doctor, "distro", lambda: doctor.DEBIAN)
    missing = lambda name: None  # noqa: E731
    present = lambda name: "libxcb-cursor.so.0"  # noqa: E731
    assert doctor.check_display({"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"},
                                missing) is None
    c = doctor.check_display({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, missing)
    assert c.status == doctor.FAIL and c.fix == "sudo apt install libxcb-cursor0"
    assert doctor.check_display({"DISPLAY": ":0"}, present).status == doctor.OK


def test_missing_required_decoder(monkeypatch):
    monkeypatch.setattr(doctor, "ffmpeg_decoders", lambda: {"aac", "mp3", "flac", "vorbis", "pcm_s16le"})
    checks = {c.name: c for c in doctor.check_ffmpeg()}
    assert checks["Audio decoders"].status == doctor.FAIL and "Opus" in checks["Audio decoders"].detail
    assert checks["Optional decoders"].status == doctor.WARN


def test_exit_status_reflects_failures(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_all", lambda gpu: [doctor.Check("a", doctor.OK, "fine")])
    assert doctor.main(argparse.Namespace(no_gpu=True)) == 0
    monkeypatch.setattr(doctor, "run_all", lambda gpu: [doctor.Check("a", doctor.FAIL, "bad", "fix it")])
    assert doctor.main(argparse.Namespace(no_gpu=True)) == 1
    assert "fix it" in capsys.readouterr().out


def test_data_dir_reports_free_space():
    from echo_app.settings import Settings

    (c,) = doctor.check_data_dir(Settings())
    assert c.status in (doctor.OK, doctor.WARN) and "GB free" in c.detail

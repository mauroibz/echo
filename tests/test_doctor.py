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
    checks = doctor.check_ffmpeg()
    assert checks[0].status == doctor.FAIL and "dnf install" in checks[0].fix


def test_missing_pipewire_fails(monkeypatch):
    monkeypatch.setattr(doctor, "_which", _fake_which({"pw-record"}))
    c = doctor.check_pipewire()
    assert c.status == doctor.FAIL and "pipewire-utils" in c.fix


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

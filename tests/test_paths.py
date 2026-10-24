"""Where Echo keeps things on Linux and on Windows."""

from pathlib import Path

from echo_app import paths


def test_windows_folders(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "WINDOWS", True)
    for var in ("ECHO_DATA_DIR", "ECHO_CONFIG_DIR", "ECHO_STATE_DIR", "ECHO_RUNTIME_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "me"))
    assert paths.config_dir() == tmp_path / "Roaming" / "Echo"
    assert paths.state_dir() == tmp_path / "Local" / "Echo" / "state"
    assert paths.cache_dir() == tmp_path / "Local" / "Echo" / "cache"
    assert paths.default_data_dir() == tmp_path / "me" / "Documents" / "Echo"
    assert paths.runtime_dir() == tmp_path / "Local" / "Echo" / "run" and paths.runtime_dir().is_dir()


def test_linux_folders(monkeypatch, isolated_home):
    monkeypatch.setattr(paths, "WINDOWS", False)
    assert paths.config_dir() == Path(isolated_home) / ".config" / "echo"
    assert paths.default_data_dir() == Path(isolated_home) / ".local" / "share" / "echo"

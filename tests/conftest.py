import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own HOME and XDG dirs; nothing touches the real user data."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    for var in ("ECHO_DATA_DIR", "ECHO_CONFIG_DIR", "ECHO_STATE_DIR"):
        monkeypatch.delenv(var, raising=False)
    # XDG_RUNTIME_DIR stays real: PipeWire's socket lives there.
    return home

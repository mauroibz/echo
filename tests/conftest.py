import os

import pytest

# Captured before any test swaps HOME, for tests that need the real model cache.
REAL_HF_HOME = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own HOME and XDG dirs; nothing touches the real user data."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Windows takes its folders from these instead of HOME and XDG.
    for var, sub in (("USERPROFILE", ""), ("APPDATA", "AppData/Roaming"), ("LOCALAPPDATA", "AppData/Local")):
        monkeypatch.setenv(var, str(home / sub) if sub else str(home))
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    for var in ("ECHO_DATA_DIR", "ECHO_CONFIG_DIR", "ECHO_STATE_DIR"):
        monkeypatch.delenv(var, raising=False)
    # XDG_RUNTIME_DIR stays real (PipeWire's socket lives there); Echo's own locks do not.
    monkeypatch.setenv("ECHO_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("ECHO_NO_WORKER", "1")
    monkeypatch.setenv("ECHO_NO_PORTAL", "1")  # never ask the real desktop for shortcuts
    # Echo alone, even in a checkout with an extension next to it; tests/test_extensions.py loads fakes.
    monkeypatch.setenv("ECHO_NO_EXTENSIONS", "1")
    # No animation unless a test asks for it (tests/test_motion.py): states are final at once.
    monkeypatch.setenv("ECHO_REDUCE_MOTION", "1")
    return home


@pytest.fixture
def real_models(monkeypatch):
    monkeypatch.setenv("HF_HOME", REAL_HF_HOME)

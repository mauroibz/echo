# Tasks

## 1. Project scaffolding

- [x] 1.1 Create `pyproject.toml` (src layout, `echo-app` entry point, `worker` extra, uv settings: managed Python only, no build), `.python-version`, `.gitignore`; verify `uv lock` produces `uv.lock` and `uv sync --locked --no-build` succeeds
- [x] 1.2 Add `echo_app.paths` (XDG data/config/state dirs, overridable by env for tests) and verify with unit tests

## 2. Settings and library storage

- [x] 2.1 Implement settings load/save with defaults, unknown-key tolerance and corrupt-file backup; verify unit tests cover each scenario in the library-storage spec
- [x] 2.2 Implement atomic file writes and the recording folder model (`meta.json`, id format, create/load/update); verify kill-safety by unit test that interrupts between temp write and rename
- [x] 2.3 Implement the SQLite index (schema versioning, upsert, list, rescan from folders, pending-transcription marker); verify deleting the index and rescanning restores the library in a test
- [x] 2.4 Implement recoverable delete (freedesktop trash or data-dir fallback); verify by test against a temporary HOME

## 3. CLI, doctor and installer

- [x] 3.1 Implement `echo-app` CLI with `rescan`, `list`, `doctor` and `--version`; verify `echo-app --help` lists them
- [x] 3.2 Implement doctor checks (pw-record, ffmpeg + decoders, interpreter, lock sync, disk, data dir writable) with fix hints and exit status; verify by tests that stub missing tools
- [x] 3.3 Write `install.sh` and `uninstall.sh` (profiles, launchers, desktop entry, icon, `--purge`); verify a full base install and uninstall into a throwaway HOME leaves `/usr` untouched and recordings intact
- [x] 3.4 Write README with install, update and uninstall instructions; verify the commands in it run as written

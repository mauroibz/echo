# The installer chooses the extensions

## Why

Echo Studio will live in the same repository as Echo. Its presence in the clone can no longer
mean it is wanted: the installer has to decide, and `doctor` has to say what was decided.

## What Changes

- `install.sh --with-studio` / `--without-studio`, remembered in `.install-extensions` like the
  transcription profile; `uninstall.sh` removes the file.
- The launcher passes the choice as `ECHO_EXTENSIONS`; Echo loads only the extensions named.
  Without the launcher, every known extension present loads, as before.
- `echo-app doctor` adds an "Extensions" line.

## Capabilities

### Modified Capabilities

- `installation`

## Impact

`install.sh`, `uninstall.sh`, `bin/echo-app`, `.gitignore`, `src/echo_app/extensions.py`,
`src/echo_app/doctor.py`, `tests/test_extensions.py`, `docs/design.md`, `CHANGELOG.md`.

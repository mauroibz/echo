# Proposal

## Why

Echo needs a base that every later milestone builds on: a reproducible per-user install, a
self-check that tells a new machine what is missing, and an on-disk library format that is
the source of truth for recordings and transcripts. Getting these right first keeps later
features from inventing their own storage or install steps.

## What Changes

- New Python project managed by uv with a committed, hash-locked `uv.lock`, a pinned
  uv-managed CPython, and two install profiles (base app, and app plus transcription worker).
- `install.sh` that installs into the clone and `~/.local` only, plus a matching uninstall.
- `echo-app doctor`: a pass/fail report of system prerequisites and install health.
- Library storage: XDG data directory, one folder per recording with `meta.json`, and a
  rebuildable SQLite index with `echo-app rescan`.
- Settings stored in one small file with defaults for every key.

## Capabilities

### New Capabilities
- `installation`: per-user install and uninstall, dependency pinning, and the doctor self-check.
- `library-storage`: on-disk layout of recordings, metadata, the rebuildable index, and settings.

### Modified Capabilities

## Impact

New repository content: `pyproject.toml`, `uv.lock`, `.python-version`, `install.sh`,
`src/echo_app/` package. Requires `uv` on the host. No system packages are modified.

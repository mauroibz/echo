# Proposal

## Why

After Windows, macOS needs only the third branch of the paths module, an installer and a test
pass: PortAudio covers the microphone, torch has Apple-silicon wheels, and `send2trash` covers
the trash.

## What Changes

- `paths.py` macOS branch (`~/Library/Application Support/Echo`, `~/Library/Caches/Echo`,
  `~/Library/Logs/Echo`), `install.sh` detecting macOS (Homebrew hints for uv and ffmpeg, an
  `.app` wrapper in `~/Applications`), an `mps` compute profile (torch Metal), and
  microphone-permission handling in doctor.
- "Computer audio" is not offered; the README points to a virtual device (BlackHole).

## Impact

`paths.py`, `install.sh`, `pyproject.toml` (profile), `doctor.py`, README. Blocked on a Mac tester.

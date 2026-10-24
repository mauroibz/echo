# Design

## Context

No Windows machine is available to the author. Verification therefore leans on CI
(`windows-latest` running the suite with the fake backend) and on a volunteer tester for the
real-audio pass; the tasks mark which is which.

## Decisions

### PortAudio backend

`sounddevice.RawInputStream(samplerate, channels, dtype="int16", callback=...)` in the
supervisor process writes blocks to the open take file; the supervisor's existing loop fsyncs
every 2 seconds, writes the heartbeat and reads the command file. Loss bound on a crash of the
supervisor is the unflushed 2 seconds, the same bound the design already accepts for a power
cut; a crash of a separate capture process no longer exists as a case. Device listing comes
from `sounddevice.query_devices()` filtered to input channels > 0, default from
`sounddevice.default.device`. The meter is a second low-rate stream, as with PipeWire. Playback
is an `OutputStream` fed from the ffmpeg decode pipe, replacing `pw-play`.

Backend selection in `audio.backend.get()`: PipeWire when `pw-dump` lists audio nodes;
otherwise PortAudio. The setting `source` stores a backend-qualified name (`pw:` or `pa:`
prefix) so a saved selection cannot be misread by the other backend.

### Detached children on Windows

`start_new_session=True` becomes `creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`;
`selfcmd.command()` uses `pythonw.exe` on Windows so children never open consoles. Stop is
the command file (no signals needed), which is why the previous refactor comes first.

### Paths and trash

| Folder | Windows |
|---|---|
| recordings | `%USERPROFILE%\Documents\Echo` (user-visible, like the Linux share dir) |
| settings | `%APPDATA%\Echo` |
| logs, state | `%LOCALAPPDATA%\Echo\state` |
| cache | `%LOCALAPPDATA%\Echo\cache` |
| runtime (locks) | `%LOCALAPPDATA%\Echo\run` |

`send2trash` on all platforms (small, pure Python); the fallback to `<data>/trash` stays.

### Installer

PowerShell, no admin: `winget install astral-sh.uv Gyan.FFmpeg` when missing, clone-local
`.venv` via `uv sync --locked` with the chosen profile, shortcut in
`%APPDATA%\Microsoft\Windows\Start Menu\Programs`, file associations under `HKCU`. Uninstall
reverses it and keeps recordings unless `-Purge`.

## Risks

- `sounddevice` wheels bundle PortAudio; WASAPI exclusive mode and sample-rate negotiation
  differ from PipeWire. The backend asks for the device's default rate and resamples with
  ffmpeg at finalize when it differs from the setting.
- Long paths and reserved names in recording titles: `export.suggested_name` already sanitizes;
  add the Windows reserved set.

## Decisions made while implementing

- **Trash**: Linux keeps Echo's own freedesktop code rather than `send2trash`, which reads the
  home folder once at import (found in the tests, where it put a deleted folder into another
  test's home). `send2trash` is used on Windows and macOS, with `<data>/trash` as the fallback.
- **CUDA on Windows**: PyPI's torch is CPU-only on Windows, so the `cuda` extra takes torch from
  PyTorch's `cu130` index there (explicit index, `sys_platform == 'win32'`); Linux is unchanged.
- **Source names**: PipeWire node names stay unprefixed, as already saved in settings; PortAudio
  sources are `pa:<host API>:<device name>` (one host API per platform: WASAPI, Core Audio,
  ALSA), so neither backend can misread the other's saved choice.
- **Sample rate**: instead of resampling at finalize, a device that refuses the requested rate is
  opened at its own, and the session takes that rate when no audio exists yet; a later take at a
  different rate is refused with a warning.
- **Backend choice**: PipeWire when `pw-record` exists and PipeWire lists audio inputs, else
  PortAudio; `ECHO_AUDIO_BACKEND=pipewire|portaudio` forces one. Doctor has an "Audio system"
  line saying which and what it means.
- **Stopping a capture process on Windows** uses CTRL_BREAK_EVENT for its process group, then
  kill; `tests/fake_capture.py` handles SIGBREAK.
- **Launcher**: `bin/echo-app.pyw` (pythonw for the Start Menu, python for the `echo-app.cmd`
  shim in `%LOCALAPPDATA%\Echo\bin`), since a shortcut cannot set `PYTHONPATH`.
- **Installer parameter** `-Compute cuda|cpu` rather than `-Profile`, which PowerShell reserves.
- **The single-instance socket** is named after the account on Windows (there is no uid).
- **Known limit, to settle with a Windows tester**: if the device's rate changes in the middle
  of a recording (another program switches the shared-mode format), new takes cannot join the
  recording, which has one rate; the supervisor says so and keeps retrying. Keeping such takes and
  resampling them at finalize is the fix if it happens in practice.

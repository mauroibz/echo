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

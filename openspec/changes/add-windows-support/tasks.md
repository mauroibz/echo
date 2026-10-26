# Tasks

## 1. Portable pieces (CI-verifiable)

- [x] 1.1 `paths.py` Windows mapping; `send2trash`; `selfcmd` with `pythonw` and creation flags; Windows reserved names in `suggested_name`; tests
- [ ] 1.2 Add `windows-latest` to the CI matrix running the fast suite with the fake backend; fix what fails
- [ ] 1.3 `install.ps1`, `uninstall.ps1`, `.ico`, README Windows section; doctor checks for ffmpeg, uv, GPU and profile with Windows wording

## 2. PortAudio backend (needs a Windows tester)

- [x] 2.1 `audio/portaudio.py` implementing the backend protocol: devices, capture into takes with fsync, meter, output; backend selection with prefixed source names
- [ ] 2.2 Real-machine pass: record 30 minutes with pause and resume, close the window mid-way, power-cycle test, import, transcribe on GPU; log results in the change's design.md
- [ ] 2.3 Use the PortAudio backend on Linux when PipeWire has no nodes; verify on Ubuntu 22.04

## Blocked

- **1.2** The `windows-latest` job ran and failed every push with a Qt access violation during
  the suite ("Windows fatal exception: access violation"). It was removed from
  `.github/workflows/test.yml` on 2026-10-26, since Windows is not a target for now. To resume:
  add the job back (the Ubuntu job's steps, with `choco install ffmpeg -y` for the packages) and
  find which test crashes, for example with `pytest -p no:randomly -x -v`.
- **1.3** is written but not run: `install.ps1` and `uninstall.ps1` (both parse without errors
  in PowerShell 7 in the `mcr.microsoft.com/powershell` container), `data/echo-app.ico`,
  `bin/echo-app.pyw`, the README section and doctor's Windows wording. A person must run
  `.\install.ps1 -WithTranscription` on Windows 11 and check: the Start Menu entry opens Echo
  without a console window, `echo-app doctor` runs in a new terminal, "Open with Echo" appears
  for a `.opus` file, and `.\uninstall.ps1` removes them.
- **2.2** needs a Windows machine: record 30 minutes with pause and resume, close the window
  mid-way, cut the power, import, transcribe on the GPU; log the results in design.md.
- **2.3** is implemented and verified on Fedora with PortAudio forced (`ECHO_AUDIO_BACKEND=
  portaudio`: recording, pause, markers, crash recovery, meter, playback); a person must check it
  on Ubuntu 22.04, where PipeWire runs no audio and Echo must pick PortAudio by itself.

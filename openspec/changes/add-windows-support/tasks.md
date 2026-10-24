# Tasks

## 1. Portable pieces (CI-verifiable)

- [ ] 1.1 `paths.py` Windows mapping; `send2trash`; `selfcmd` with `pythonw` and creation flags; Windows reserved names in `suggested_name`; tests
- [ ] 1.2 Add `windows-latest` to the CI matrix running the fast suite with the fake backend; fix what fails
- [ ] 1.3 `install.ps1`, `uninstall.ps1`, `.ico`, README Windows section; doctor checks for ffmpeg, uv, GPU and profile with Windows wording

## 2. PortAudio backend (needs a Windows tester)

- [ ] 2.1 `audio/portaudio.py` implementing the backend protocol: devices, capture into takes with fsync, meter, output; backend selection with prefixed source names
- [ ] 2.2 Real-machine pass: record 30 minutes with pause and resume, close the window mid-way, power-cycle test, import, transcribe on GPU; log results in the change's design.md
- [ ] 2.3 Use the PortAudio backend on Linux when PipeWire has no nodes; verify on Ubuntu 22.04

## ADDED Requirements

### Requirement: Windows installation
On Windows, `install.ps1` SHALL install Echo for the current user without administrator
rights, obtaining uv and ffmpeg if missing, creating a Start Menu entry and file
associations, and SHALL be reversible with `uninstall.ps1`, which keeps recordings unless
told otherwise. Transcription profiles SHALL be the same as on Linux except `rocm`.

#### Scenario: Fresh Windows machine
- **WHEN** the user runs `install.ps1 -WithTranscription` on a machine with an NVIDIA GPU
- **THEN** Echo appears in the Start Menu, records from the microphone, and transcribes on the GPU

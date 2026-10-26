## ADDED Requirements

### Requirement: Record a call from the command line
`echo-app record --computer-audio` SHALL record the computer audio as a second track next to the
chosen input, as the window does, and `--no-computer-audio` SHALL record the input alone. Without
either flag the remembered choice SHALL apply, as the remembered source does. `echo-app info
--json` SHALL report a recording's tracks.

#### Scenario: Scripted call recording
- **WHEN** a script runs `echo-app record --computer-audio`, then `echo-app stop`, then `echo-app info <id> --json`
- **THEN** the recording has two channels and the JSON lists the tracks as microphone and computer audio

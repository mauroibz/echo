## MODIFIED Requirements

### Requirement: Recording independent of the window
Recording SHALL run in a process separate from the window, controlled through files in the
recording folder (a command file for pause, resume and stop; a status file with a heartbeat).
Closing the window, a crash of the window or of the CLI SHALL NOT stop or damage the
recording. A new window or CLI SHALL find the running recording from its folder and status
file alone, without inspecting the process table.

#### Scenario: Window closed while recording
- **WHEN** the window is closed during a recording
- **THEN** the recording continues and the reopened window shows it as recording with the correct elapsed time

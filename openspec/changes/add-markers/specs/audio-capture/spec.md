## ADDED Requirements

### Requirement: Markers while recording
While recording, one key press SHALL add a marker at the current position in the captured
audio, correct across pauses and capture gaps, with an optional note that can be typed without
interrupting the recording. Markers SHALL be saved with the recording as it is finalized and
SHALL survive a crash like the audio does.

#### Scenario: Mark during a paused stretch
- **WHEN** the user pauses at 10:00, resumes, and presses the marker key 5 seconds later
- **THEN** a marker is stored at 10:05 of the captured audio

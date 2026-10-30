## ADDED Requirements

### Requirement: Motion
Changes of state SHALL be shown with short motion (120 to 420 ms): the recorder entering and
leaving recording, a pulsing dot while recording and a slow amber blink while paused, a ring on
the marker button and a marker dropping onto the waveform, a new recording sliding into the
list, a sweep along a running transcription's progress, the play icon crossing to pause,
smooth scrolling to the passage that plays, Details sliding open and closed, and messages fading.
A "Reduce motion" setting, on by itself when the desktop has animations turned off, SHALL stop
all of it while the time, levels and progress still update. Nothing SHALL animate while the
window is hidden.

#### Scenario: Recording starts
- **WHEN** the user presses Record
- **THEN** the recorder's coral block fades in and the dot beside "RECORDING" pulses until Pause or Stop

#### Scenario: Reduce motion
- **WHEN** GNOME's animations are off and the user presses Record
- **THEN** the recorder shows the recording state at once and the dot stays still, and the time still counts

## MODIFIED Requirements

### Requirement: Closing never stops a recording
Closing the window while recording SHALL keep the recording running and show the recording dock
(and, where there is one, the tray icon). Reopening Echo SHALL show the recording in progress.

#### Scenario: Close during recording
- **WHEN** the user closes the window during a recording
- **THEN** the recording continues, the dock shows its time with Pause, Stop and Marker, a tray
  icon offers to show Echo or stop the recording, and no audio is lost

## ADDED Requirements

### Requirement: Recording dock
A small dock SHALL let the user record without the window: at rest, Record and the input; while
recording, the time, the level, what is recorded, Marker with a count, Pause, Stop and a way back
to the window; while paused, the time blinking in amber; after Stop, that the recording was
saved and its transcription progress, with Open and Done. It SHALL float above other windows
where the desktop allows it, be moved by dragging, remember its place, shrink to the time while
recording when the pointer is away, and show problems with the input. Ctrl+Shift+D SHALL swap the
window and the dock.

#### Scenario: Record a call from the dock
- **WHEN** the user presses Ctrl+Shift+D, then Record in the dock, marks twice and presses Stop
- **THEN** the window is hidden throughout, the dock shows the time and "2" beside Marker, and after Stop it says the recording was saved, and Open shows it selected in the window

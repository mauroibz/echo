## MODIFIED Requirements

### Requirement: Recording dock
A small dock SHALL let the user record without the window: at rest, Record and the input; while
recording, the time, the level, what is recorded, Marker with a count, Notes, Pause, Stop and a
way back to the window; while paused, the time blinking in amber; after Stop, that the recording
was saved and its transcription progress, with Open and Done. It SHALL float above other windows
where the desktop allows it, be moved by dragging, remember its place, shrink to the time while
recording when the pointer is away and its notes are closed, and show problems with the input.
Ctrl+Shift+D SHALL swap the window and the dock.

Notes SHALL open a field under the dock with the recording's notes, saved as they are typed and
when the field closes, the dock hides or the recording stops; the window SHALL show them when it
comes back. Ctrl+T in the field SHALL write the recording's time where the cursor is, as
"[m:ss] ", on a line of its own. With "Switch to the recording dock when a recording starts" on, the window SHALL give
way to the dock whenever a recording other than a quick note starts.

#### Scenario: Record a call from the dock
- **WHEN** the user presses Ctrl+Shift+D, then Record in the dock, marks twice and presses Stop
- **THEN** the window is hidden throughout, the dock shows the time and "2" beside Marker, and after Stop it says the recording was saved, and Open shows it selected in the window

#### Scenario: A note during the call
- **WHEN** the user presses Notes in the dock while recording, types "Precio: revisar el plan anual" and goes back to the window
- **THEN** the recording's notes have that line, and Details shows it

#### Scenario: A note with its time
- **WHEN** the recording is at 12:34 and the user presses Ctrl+T in the dock's notes and types "precio"
- **THEN** the notes end with the line "[12:34] precio"

#### Scenario: Always the dock
- **WHEN** the setting is on and the user presses Record in the window
- **THEN** the window hides and the dock shows the recording

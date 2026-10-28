## MODIFIED Requirements

### Requirement: Input level monitoring
Echo SHALL show a live peak level of the selected source, updating at least ten times per
second, both before and during recording, and SHALL indicate clipping. Before recording, the
meter SHALL run while the Echo window is shown, including while one of its dialogs is open, and
SHALL stop while the window is minimized or hidden. When the input has delivered exact digital
silence for four seconds, Echo SHALL say so on the meter, without moving the controls around
it, with the advice to check the connection, mute and gain in its tooltip; the welcome screen
SHALL show that advice under its meter. The user SHALL be able to listen to the selected input
through the current output device, and listening SHALL be off by default.

#### Scenario: Checking the microphone
- **WHEN** the user selects a source while not recording
- **THEN** the level meter moves with the input within half a second

#### Scenario: Meter on the welcome screen
- **WHEN** the welcome screen is open on first launch
- **THEN** its level meter moves with the selected input

#### Scenario: Silent input
- **WHEN** the selected input sends only digital silence for four seconds
- **THEN** the meter reads "No sound for 4 s", its tooltip says what to check, and nothing else in the sidebar moves

#### Scenario: A noise gate
- **WHEN** the user records through a noise gate that is closed between sentences
- **THEN** the note on the meter comes and goes with the pauses and the controls stay where they are

## MODIFIED Requirements

### Requirement: Input level monitoring
Echo SHALL show a live peak level of the selected source, updating at least ten times per
second, both before and during recording, and SHALL indicate clipping. Before recording, the
meter SHALL run while the Echo window is shown, including while one of its dialogs is open, and
SHALL stop while the window is minimized or hidden. When the input has delivered exact digital
silence for four seconds, Echo SHALL say so next to the meter and suggest checking the
connection, mute and gain. The user SHALL be able to listen to the selected input through the
current output device, and listening SHALL be off by default.

#### Scenario: Checking the microphone
- **WHEN** the user selects a source while not recording
- **THEN** the level meter moves with the input within half a second

#### Scenario: Meter on the welcome screen
- **WHEN** the welcome screen is open on first launch
- **THEN** its level meter moves with the selected input

#### Scenario: Silent input
- **WHEN** the selected input sends only digital silence for four seconds
- **THEN** a hint under the meter says no sound is arriving and what to check

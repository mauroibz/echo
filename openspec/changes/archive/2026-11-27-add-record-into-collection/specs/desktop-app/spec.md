## ADDED Requirements

### Requirement: Recording into a collection
Under Record the window SHALL name where new recordings are filed (the day-to-day list or a
collection) and let the user change it before recording: any collection, a new name, or the list.
The choice SHALL persist and apply to every recording started afterwards, from the window, the
dock, the tray, the system-wide shortcut, the command line or an extension; a quick note SHALL
never be filed. The recording SHALL carry its collection from the moment it starts, SHALL show in
the list while it is made wherever the list is, and the list SHALL open its collection when it
starts. Renaming the chosen collection SHALL move the choice with it, and emptying it SHALL set the
choice back to the day-to-day list.

#### Scenario: A client's meetings by default
- **WHEN** the user chooses New collection… under Record, names it IHSA, and later presses Record three times over a week
- **THEN** the three recordings are in IHSA, which the list shows each time, and the day-to-day list has none of them

#### Scenario: Killed while recording
- **WHEN** Echo is killed during a recording started with IHSA chosen and the recording is recovered
- **THEN** it is in IHSA

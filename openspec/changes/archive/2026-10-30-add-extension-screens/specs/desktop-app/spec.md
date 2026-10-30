## ADDED Requirements

### Requirement: Screens and passages for extensions
An extension SHALL be able to add a screen shown in place of the selected recording, opened and
closed by a button beside People and closed by choosing a recording in the list; to show a
recording playing from a time; to add sections under a person's notes in People; and to get the
passages matching a search with their recording, times, speaker and text. Without an extension
the window SHALL be unchanged.

#### Scenario: A citation
- **WHEN** an extension's screen calls `show_recording(id, at=12.5)`
- **THEN** the screen closes, the recording is selected and plays from 0:12

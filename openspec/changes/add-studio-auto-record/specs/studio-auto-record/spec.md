## ADDED Requirements

### Requirement: Meetings record themselves
With the setting on and Echo running, a calendar event with a video link SHALL start a recording
titled after it when it starts (or within its first 10 minutes, if Echo was not running at the
start), unless something is being recorded, the user skipped it, or Studio already started it
once. Studio SHALL stop a recording it started 10 minutes after the event ends, unless the user
stopped it.

#### Scenario: The 15:00 call
- **WHEN** "Roadmap review" with a Teams link starts at 15:00 and Echo is in the tray
- **THEN** Echo records "Roadmap review" from 15:00, the tray says so, and the recording stops at 15:55 if the user has not stopped it

#### Scenario: Not this one
- **WHEN** the user presses Skip on the home before the meeting
- **THEN** nothing is recorded, also after restarting Echo

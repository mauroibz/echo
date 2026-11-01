## MODIFIED Requirements

### Requirement: Meetings record themselves
With Echo running, Studio SHALL start a recording titled after a calendar event when it starts
(or within its first 10 minutes, if Echo was not running at the start) if either:
- the event has a video link, the setting is on and the user did not switch it off; or
- the user switched it on.

It SHALL NOT start one while something is being recorded, or for an event Studio already started
once. Studio SHALL stop a recording it started 10 minutes after the event ends, unless the user
stopped it. The user's switches SHALL survive restarting Echo.

#### Scenario: The 15:00 call
- **WHEN** "Roadmap review" with a Teams link starts at 15:00 and Echo is in the tray
- **THEN** Echo records "Roadmap review" from 15:00, the tray says so, and the recording stops at 15:55 if the user has not stopped it

#### Scenario: Not this one
- **WHEN** the user switches the meeting off in Coming up, or presses Don't record, before it starts
- **THEN** nothing is recorded, also after restarting Echo

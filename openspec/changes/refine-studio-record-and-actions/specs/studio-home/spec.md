## MODIFIED Requirements

### Requirement: Studio's window
With a summaries server or a calendar set, the window SHALL show a rail with Record at the top,
then Briefing, Recordings and People, opening on Briefing; Recordings SHALL be Echo's window
unchanged. Record SHALL start and stop a recording from any page and SHALL show the elapsed time
while recording. Without a server or a calendar, the window SHALL be Echo's. Showing a recording
from anywhere SHALL go to Recordings.

#### Scenario: Recording from the Briefing
- **WHEN** the user is on the Briefing and presses Record at the top of the rail
- **THEN** recording starts without leaving the Briefing, the rail shows the time under Record, and pressing it again on any page stops

## ADDED Requirements

### Requirement: Recording a meeting under way
While the next meeting is under way and not being recorded, the Briefing's hero SHALL offer
Record this meeting, naming the recording after it. The hero SHALL NOT offer another way to start
a recording: the rail's Record does that.

#### Scenario: Joined late
- **WHEN** "Sync de producto" started five minutes ago, was skipped, and the user opens the Briefing
- **THEN** the hero shows Record this meeting, and the recording it starts is titled "Sync de producto"

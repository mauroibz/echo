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

### Requirement: Record now on the Briefing
While nothing is being recorded, the Briefing's hero SHALL have Record now. While the next
meeting is under way and not being recorded, the button SHALL read Record this meeting and name
the recording after it.

#### Scenario: No calendar
- **WHEN** no calendar is set and the user opens Studio
- **THEN** the hero shows Record now beside Add your calendar

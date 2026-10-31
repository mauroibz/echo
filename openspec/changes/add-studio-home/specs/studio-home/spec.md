## ADDED Requirements

### Requirement: Studio's window
With a summaries server or a calendar set, the window SHALL show a rail with Home, Recordings,
People, Ask and Record, opening on Home; Recordings SHALL be Echo's window unchanged. Without
either, the window SHALL be Echo's. Showing a recording from anywhere SHALL go to Recordings.

#### Scenario: Turning Studio on
- **WHEN** the user sets a calendar address in Settings and presses OK
- **THEN** the rail appears on Home, and Recordings shows the same list and selection as before

### Requirement: Home
Home SHALL show the next meeting from the calendar with its time, title, invitation text without
links, attendees, a Join button for its video link and whether it will record by itself (with
Skip); while recording, the elapsed time, notes saved to the recording, and who was invited; and
below, the minutes of the latest recordings with their excerpt, people and number of action
items. It SHALL NOT show suggestions, reminders or overdue items.

#### Scenario: Twenty-five minutes before the call
- **WHEN** "Roadmap review" with a Teams link starts in 25 minutes
- **THEN** Home says "UP NEXT IN 25 MIN", shows 15:00 large, the attendees, Join the call and "Records by itself at 15:00" with Skip

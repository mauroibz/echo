## MODIFIED Requirements

### Requirement: Studio's window
With a summaries server or a calendar set, the window SHALL show a rail with Briefing, Recordings,
People and Record, opening on Briefing; Recordings SHALL be Echo's window unchanged. Without
either, the window SHALL be Echo's. Showing a recording from anywhere SHALL go to Recordings.

#### Scenario: Turning Studio on
- **WHEN** the user sets a calendar address in Settings and presses OK
- **THEN** the rail appears on Briefing, and Recordings shows the same list and selection as before

### Requirement: Home
The Briefing SHALL show:
- The next meeting from the calendar: its time, title, invitation text without links, attendees,
  a Join button for its video link, and whether it will record by itself, with Don't record or
  Record it.
- While recording: the elapsed time, notes saved to the recording, and who was invited.
- The minutes of the latest recordings as cards. Each card SHALL have the minutes' excerpt, up to
  three action items that are not discarded (with owner and due date) and how many more, the
  user's notes, the people, the tags and a star.

It SHALL NOT show suggestions, reminders or overdue items.

#### Scenario: Twenty-five minutes before the call
- **WHEN** "Roadmap review" with a Teams link starts in 25 minutes
- **THEN** the Briefing says "UP NEXT IN 25 MIN", shows 15:00 large, the attendees, Join the call and "Records by itself at 15:00" with Don't record

#### Scenario: A glance at yesterday's sync
- **WHEN** yesterday's "Product sync" has five action items and notes
- **THEN** its card shows the gist, the first three items with their owners, "+2 more" and the start of the notes

## ADDED Requirements

### Requirement: Coming up
With a calendar set, the Briefing SHALL list the meetings of the next 7 days by day, each with its
time, title, length, whether it has a video link, the first attendees, and a switch for whether
it is recorded when it starts. A meeting being recorded or already started SHALL show that
instead of the switch.

#### Scenario: An in-person lunch
- **WHEN** tomorrow has "Almuerzo con proveedores" without a link and "Sync de producto" with one
- **THEN** the lunch's switch is off and the sync's is on, and switching the lunch on records it when it starts

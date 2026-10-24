## MODIFIED Requirements

### Requirement: Library list
The list SHALL show recordings newest first, grouped by month, with title, date, duration and
status, and SHALL filter by search text and by tags shown as chips above it. Selecting a
recording SHALL show its tags, notes and statistics (words, words per minute, silence share).

#### Scenario: Filter by tag
- **WHEN** the user clicks the "entrevista" chip
- **THEN** only recordings with that tag are listed, and the chip shows as active until cleared

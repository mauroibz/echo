## ADDED Requirements

### Requirement: Passages the user should check are marked
The transcript SHALL mark passages whose text is implausibly short for their duration, whose
kept text came from a retry, or whose model confidence is low, with the reason. The marks
SHALL be advisory: shown in the editor, counted, navigable, and cleared for a passage once the
user edits it.

#### Scenario: Short passage
- **WHEN** a 12-second passage yields three words after all retries
- **THEN** it is marked "short" in the transcript and shaded in the editor with that reason

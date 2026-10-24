## ADDED Requirements

### Requirement: Record from anywhere
With Echo running, a system-wide shortcut SHALL start and stop recording, and a quick-note
shortcut SHALL record until pressed again and copy the finished transcript to the clipboard
with a notification. Recordings not renamed by the user SHALL be titled from their first
sentence once transcribed.

#### Scenario: Quick note
- **WHEN** the user presses the quick-note shortcut, speaks for twenty seconds, and presses it again
- **THEN** a notification appears when the text is ready, the text is on the clipboard, and the recording is in the library with a title taken from its first sentence

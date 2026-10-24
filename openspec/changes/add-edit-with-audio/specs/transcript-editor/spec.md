## ADDED Requirements

### Requirement: Edit with the audio
From the keyboard, the user SHALL be able to play the passage under the cursor, move to the
previous or next passage and play it, and jump to the next flagged passage. Playback SHALL
pause while the user types and resume from the start of the passage when typing stops, unless
turned off in settings.

#### Scenario: Correct a word
- **WHEN** the user presses the play-passage shortcut, hears the passage, and starts typing
- **THEN** playback pauses, the edit autosaves, and a second later the passage plays again from its start

## MODIFIED Requirements

### Requirement: Layout persists
Window size, pane sizes, the selected recording and playback speed SHALL be restored on the next
launch. Each recording's and each linked set's volume SHALL be remembered and restored when it is
selected; one that was never changed plays at 100%.

#### Scenario: Reopen
- **WHEN** the user resizes the panes, quits and reopens Echo
- **THEN** the panes have the same sizes and the same recording is selected

#### Scenario: Volume follows the recording
- **WHEN** the user sets a quiet meeting to 300%, selects a voice note, then the meeting again
- **THEN** the voice note plays at 100% and the meeting at 300%, also after Echo is restarted

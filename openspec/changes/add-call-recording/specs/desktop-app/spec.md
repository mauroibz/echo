## MODIFIED Requirements

### Requirement: Recording controls
The recorder area SHALL offer source selection, a live level meter with clip indication, a listen
toggle, record, pause and stop, the elapsed recorded time, and any recorder warning. When the
source is an input and computer audio can be recorded, it SHALL offer a toggle to also record the
computer audio and, while that is on, a second level meter for it. While recording, the window
title and a tray icon SHALL show that recording is in progress.

#### Scenario: Record from the window
- **WHEN** the user presses Record, speaks, and presses Stop
- **THEN** the new recording appears at the top of the library, becomes playable when saved, and
  is queued for transcription if enabled

#### Scenario: Record a call from the window
- **WHEN** the user turns on computer audio, presses Record during a call, and presses Stop
- **THEN** both meters moved during the call, and the new recording plays both sides

# Spec Delta

## Purpose
Shows the transcript of the selected recording and lets the user correct, copy and export it
without risk of losing their edits.

## ADDED Requirements

### Requirement: Show the transcript
Selecting a recording SHALL show its transcript next to the player: the user's edited text if any,
otherwise the model transcript with paragraph breaks. Queued, running, failed and missing
transcripts SHALL each show a clear state with the relevant action (transcribe, cancel, retry,
download the model).

#### Scenario: Open a transcribed recording
- **WHEN** the user clicks a transcribed recording
- **THEN** its transcript appears in the editor immediately

### Requirement: Edit with autosave
Edits SHALL be saved automatically within two seconds of the last keystroke and on switching
recordings or quitting. Undo and redo SHALL work. The editor SHALL show whether the text is the
model output or edited.

#### Scenario: Edit and switch
- **WHEN** the user corrects a word and immediately selects another recording
- **THEN** the correction is saved and appears when the first recording is selected again

### Requirement: Never overwrite edits
Re-transcribing SHALL not change the user's edited text. When a newer model transcript exists the
editor SHALL say so and offer to switch to it. Reverting to the model output SHALL ask for
confirmation and remain undoable until the recording is switched.

#### Scenario: Revert
- **WHEN** the user chooses "Revert to model output" and confirms
- **THEN** the editor shows the model transcript and the edited file is removed

### Requirement: Copy, find and export
The user SHALL be able to copy the whole transcript as plain text, find text with highlighting, and
export to a `.txt` or `.md` file.

#### Scenario: Copy all
- **WHEN** the user presses Copy
- **THEN** the clipboard holds the transcript as plain text with paragraph breaks

### Requirement: Follow along
While unedited model text is shown, the passage being played SHALL be highlighted, and clicking a
passage with Ctrl held SHALL move playback to its start.

#### Scenario: Ctrl+click to seek
- **WHEN** the user Ctrl+clicks the third paragraph
- **THEN** playback jumps to the start of that passage

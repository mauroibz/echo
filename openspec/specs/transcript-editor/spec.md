# transcript-editor Specification

## Purpose
Shows the transcript of the selected recording and lets the user correct, copy and export it
without risk of losing their edits.

## Requirements

### Requirement: Show the transcript
The transcript panel SHALL show the user's edited text when it exists, else the corrected
model text with each dictionary correction underlined, else the model text. Under the title
it SHALL offer one optional line, "Who is speaking, what about", saved with the recording and
used as context for its transcriptions. Under the editor it SHALL show at most one dictionary
candidate chip at a time.

#### Scenario: Context line
- **WHEN** the user writes "Entrevista con Lucía sobre PipeWire" in the line and transcribes again
- **THEN** that line precedes the dictionary sentence in the request's context

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

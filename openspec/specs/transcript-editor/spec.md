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
The user SHALL be able to copy the whole transcript, copy it with passage timestamps, find text
in it, and export it as plain text, Markdown, SRT, VTT or JSON with passage times. A margin
with passage start times SHALL be available with a toggle. Exports SHALL use the edited text
when it exists.

#### Scenario: Subtitles from an edited transcript
- **WHEN** the user edits a transcript and exports it as SRT
- **THEN** the file contains the edited text in cues whose times match the passages

### Requirement: Follow along
While unedited model text is shown, the passage being played SHALL be highlighted, and clicking a
passage with Ctrl held SHALL move playback to its start.

#### Scenario: Ctrl+click to seek
- **WHEN** the user Ctrl+clicks the third paragraph
- **THEN** playback jumps to the start of that passage

### Requirement: Edit with the audio
From the keyboard, the user SHALL be able to play the passage under the cursor, move to the
previous or next passage and play it, and jump to the next flagged passage. Playback SHALL
pause while the user types and resume from the start of the passage when typing stops, unless
turned off in settings.

#### Scenario: Correct a word
- **WHEN** the user presses the play-passage shortcut, hears the passage, and starts typing
- **THEN** playback pauses, the edit autosaves, and a second later the passage plays again from its start

### Requirement: Export to a Markdown folder
The user SHALL be able to export selected recordings or the whole library to a folder as one
Markdown file per recording, with title, date, tags, people, markers as headings, optional
timestamps and a link to the audio, skipping up-to-date files, and optionally keep that folder
updated as transcripts change.

#### Scenario: Obsidian vault
- **WHEN** the user exports the library to a vault folder with sync on and later edits a transcript
- **THEN** the vault has one note per recording and the edited note is rewritten within seconds

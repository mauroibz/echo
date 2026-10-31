# transcript-editor Specification

## Purpose
Shows the transcript of the selected recording and lets the user correct, copy and export it
without risk of losing their edits.

## Requirements

### Requirement: Show the transcript
The transcript panel SHALL show the user's edited text when it exists, else the corrected
model text with each dictionary correction underlined, else the model text. Each speaker's turn
SHALL be headed by their name with a dot in their color; clicking the name SHALL offer the same
actions as before (name, merge, open profile). Details SHALL offer one optional line, "Who is
speaking, what about", saved with the recording and used as context for its transcriptions.
Under the editor it SHALL show at most one dictionary candidate chip at a time.

#### Scenario: Context line
- **WHEN** the user writes "Entrevista con Lucía sobre PipeWire" in the line in Details and transcribes again
- **THEN** that line precedes the dictionary sentence in the request's context

#### Scenario: Names over turns
- **WHEN** a meeting with Ana and Pedro is shown
- **THEN** each turn starts under the speaker's name, and clicking "Ana" offers to name, merge or open her profile

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
passage with Ctrl held SHALL move playback to its start and play. A plain click that selects
nothing SHALL move playback near the clicked word, placed by how far into its passage it is and
a little before it, without starting or stopping playback; dragging to select text SHALL not
move playback.

#### Scenario: Ctrl+click to seek
- **WHEN** the user Ctrl+clicks the third paragraph
- **THEN** playback jumps to the start of that passage

#### Scenario: Click a word
- **WHEN** playback is paused and the user clicks a word halfway through a passage
- **THEN** the playhead moves to about halfway through that passage's time, still paused, and
  Space plays from there

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

### Requirement: A set's transcript
Selecting a set SHALL show its parts' transcripts one under the other in set order, each under
a heading with the part's title, date and length. The text SHALL be editable in place, each
part's edits SHALL be saved to that part only, and no edit SHALL move text across a heading.
Find, copy, passage times, follow-along, low-confidence shading and playing the passage at the
cursor SHALL work across the whole set. Parts without a transcript SHALL show their state under
their heading. Exports of a set SHALL contain every part, with times on the set's timeline.

#### Scenario: Editing the second part
- **WHEN** the user corrects a word in the second part of a set
- **THEN** only the second recording's edited transcript changes, and selecting that part alone shows the correction

#### Scenario: Deleting across a heading
- **WHEN** the user selects text from the end of the first part to the start of the second and presses Delete
- **THEN** nothing is deleted and the parts stay separate

### Requirement: Merging speakers
The user SHALL be able to declare, from a speaker's label, that the speaker is the same person
as another speaker of the recording, and to separate them again. A merged speaker SHALL keep the
other speaker's number and name, or take this one's name when the other had none, and SHALL be
treated as one speaker everywhere: labels, the naming bar, the speaker count, exports, search by
speaker and people's recordings. Naming a merged speaker SHALL remember the voice of all its
parts. Merges SHALL be stored apart from the model's transcript and SHALL be dropped when the
recording is transcribed again.

#### Scenario: One person found twice
- **WHEN** speakers 2 and 3 are the same person and the user chooses "Same person as → Speaker 2" on speaker 3
- **THEN** the margin shows one speaker where 3 was, the status counts one fewer speaker, naming speaker 2 "Ana" names every passage of both, and the TXT export prefixes all of them with "Ana"

#### Scenario: Separate again
- **WHEN** the user chooses "Separate again" on the merged speaker
- **THEN** speaker 3 is labeled on its own again, unnamed

### Requirement: Correcting speakers in the text
From the transcript's context menu the user SHALL be able to say who said a paragraph, or a
selection of words, choosing one of the recording's speakers or someone new. A selection that
covers whole passages SHALL relabel them; one that covers part of a passage SHALL split it, the
selected words becoming a paragraph of their own with the chosen speaker. The user SHALL be able
to undo a fix and to join a paragraph with the one above. Labels, exports with estimated times
for split text, search by speaker and people's speaking times SHALL follow the fixes. Fixes SHALL
be stored with the passage, speaker, name, the words and estimated times of a split, and the
transcript they apply to; a new transcription SHALL keep them without applying them.

#### Scenario: An interruption
- **WHEN** Ana's passage reads "El precio sube ¿cuánto? un diez por ciento" and the user selects "¿cuánto?" and chooses Said by → Pedro
- **THEN** the passage shows as three paragraphs labeled Ana, Pedro and Ana, the TXT export reads the same, and searching `@pedro cuánto` finds the recording

#### Scenario: A paragraph given to the wrong person
- **WHEN** the user right-clicks a paragraph labeled Pedro and chooses Said by → Ana
- **THEN** it is labeled Ana, and if the paragraph above is Ana's the margin shows one label for both

### Requirement: Hearing a speaker shows where
Playing a speaker from the naming bar SHALL move the playhead and the transcript to the passage
played, also while the cursor is in the text.

#### Scenario: Who is speaker 2
- **WHEN** the user presses ▶ in the bar asking for speaker 2's name
- **THEN** the waveform's playhead and the time jump to their passage, and the transcript scrolls
  to it and highlights it while it plays

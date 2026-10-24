# dictionary Specification

## Purpose
Known people and terms, learned from the user's own corrections and titles, used to spell
them right in new transcripts and to fix them in existing ones, with every automatic change
visible and reversible.

## Requirements

### Requirement: Plain-text dictionary
The dictionary SHALL be a plain text file in the configuration folder holding people and
terms, each with a canonical spelling, aliases, and when it was last used. Echo SHALL read it
on every transcription request and after every edit to it.

#### Scenario: Hand edit
- **WHEN** the user adds an entry to the file in a text editor
- **THEN** the next transcription request includes it

### Requirement: Learned from corrections, offered without dialogs
When the user saves an edit, Echo SHALL compare the edited text with the model text and offer
at most one candidate at a time as an inline chip under the editor: a replaced capitalized
word, or a replacement seen before in another recording. Accepting SHALL add the entry with
the model's spelling as an alias; declining SHALL mute that word permanently. Capitalized
words typed into a title SHALL be candidates the same way. Echo SHALL never open a dialog for
this.

#### Scenario: Correcting a name
- **WHEN** the user changes "zurus" to "Surus" in a transcript and the edit saves
- **THEN** a chip under the editor offers to add "Surus"; one click adds it with alias "zurus"

#### Scenario: Not a name
- **WHEN** the user declines a candidate
- **THEN** that word is never offered again

### Requirement: Used when transcribing
Every transcription request SHALL carry a context sentence built from the dictionary, most
recently used entries first within a fixed budget, preceded by the recording's own optional
context line. The transcript SHALL record the context used.

#### Scenario: Known term in a new recording
- **WHEN** "Surus" is in the dictionary and a new recording mentioning it is transcribed
- **THEN** the model transcript spells it "Surus" and the transcript's provenance lists the context sentence

### Requirement: Corrections are visible and reversible
Echo SHALL apply aliases to the finished model transcript on a copy, never altering the model
output, SHALL underline each replacement in the editor, and SHALL let the user undo any single
replacement. A newly added alias SHALL be applied to existing transcripts without
re-transcription. The corrector SHALL not touch text the user has edited.

#### Scenario: Alias added later
- **WHEN** the user adds "Surus" with alias "zurus" and opens an older recording whose model transcript says "zurus"
- **THEN** the transcript shows "Surus" underlined, and "Undo this correction" restores "zurus" for that spot

### Requirement: Managed in settings
Settings → Dictionary SHALL list entries with their aliases and last use, and allow removing,
merging and importing from a text file.

#### Scenario: Merge duplicates
- **WHEN** the user merges "Lucia" into "Lucía Fernández"
- **THEN** one entry remains with the aliases of both

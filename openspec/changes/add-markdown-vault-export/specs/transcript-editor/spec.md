## ADDED Requirements

### Requirement: Export to a Markdown folder
The user SHALL be able to export selected recordings or the whole library to a folder as one
Markdown file per recording, with title, date, tags, people, markers as headings, optional
timestamps and a link to the audio, skipping up-to-date files, and optionally keep that folder
updated as transcripts change.

#### Scenario: Obsidian vault
- **WHEN** the user exports the library to a vault folder with sync on and later edits a transcript
- **THEN** the vault has one note per recording and the edited note is rewritten within seconds

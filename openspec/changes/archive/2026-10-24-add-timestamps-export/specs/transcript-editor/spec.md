## MODIFIED Requirements

### Requirement: Copy, find and export
The user SHALL be able to copy the whole transcript, copy it with passage timestamps, find text
in it, and export it as plain text, Markdown, SRT, VTT or JSON with passage times. A margin
with passage start times SHALL be available with a toggle. Exports SHALL use the edited text
when it exists.

#### Scenario: Subtitles from an edited transcript
- **WHEN** the user edits a transcript and exports it as SRT
- **THEN** the file contains the edited text in cues whose times match the passages

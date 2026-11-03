## MODIFIED Requirements

### Requirement: Notes and markers lead the summary
When a recording has notes or markers, they SHALL be sent ahead of the transcript (each marker
with its time, its note and the passage said around it; a note line that starts with a time, as
"[12:34]", with the passage said around that time), and the summary SHALL be asked to cover each
one. What the summary is made from SHALL include them, so a changed note or marker marks the
summary out of date. A recording with neither SHALL be summarized as before.

#### Scenario: A marked moment
- **WHEN** the user marked 0:06 with "precio" and summarizes
- **THEN** the request carries "at 0:06: precio" with the passage around it, before the transcript

#### Scenario: A note with its time
- **WHEN** the recording's notes have the line "[1:06] el cierre, revisar"
- **THEN** the request carries that line with what was said around 1:06 under it

#### Scenario: A note edited after
- **WHEN** the user edits the recording's notes after its summary was made
- **THEN** the Summary view says the summary is out of date

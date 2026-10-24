## MODIFIED Requirements

### Requirement: One folder per recording
Each recording SHALL be a folder holding its audio, a `meta.json` with title, source, creation
time, duration, hash, crop, gaps, markers, tags and notes, and its transcripts. Everything the
index knows SHALL be derivable from these files.

#### Scenario: Tags survive a rescan
- **WHEN** the index is deleted and `echo-app rescan` runs
- **THEN** every recording's tags and notes are searchable again

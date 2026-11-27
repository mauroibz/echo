## ADDED Requirements

### Requirement: Record into a collection from the command line
`echo-app record` SHALL file the recording where the window's choice says, `--collection NAME`
SHALL file it in that collection instead, and `--collection ''` in none. `--quick-note` SHALL
never file.

#### Scenario: One meeting elsewhere
- **WHEN** IHSA is the choice and `echo-app record --collection Interno` runs
- **THEN** the recording is in Interno and the choice is still IHSA

## ADDED Requirements

### Requirement: People from the command line
`echo-app people` SHALL list each person with the recordings they speak in, their tags and
notes; with `--json` as one JSON document.

#### Scenario: An agent prepares for a call
- **WHEN** a script runs `echo-app people --json`
- **THEN** each person has their name, aliases, tags, notes and a list of recording ids with seconds spoken

## ADDED Requirements

### Requirement: Search by speaker from the command line
`echo-app list` SHALL accept `@name` in its query with the same meaning as in the window.

#### Scenario: An agent looks for what Ana said
- **WHEN** a script runs `echo-app list "@ana precio" --json`
- **THEN** only the recordings where Ana said "precio" are listed

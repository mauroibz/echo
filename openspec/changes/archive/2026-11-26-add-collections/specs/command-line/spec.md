## ADDED Requirements

### Requirement: Collections from the command line
`echo-app collections` SHALL list the collections with how many recordings each holds (`--json`:
name, recording ids newest first, how many are transcribed), and with recordings and `--add NAME`
or `--remove` SHALL file them or take them out. `import --collection NAME` SHALL file what it
imports, `list --collection NAME` SHALL list only that collection (`''`: those in none),
`bundle --collection NAME` SHALL bundle all of it oldest first, and a recording's JSON SHALL
carry `collection` (its name or null). Names SHALL match without case or accents.

#### Scenario: A batch from a script
- **WHEN** `echo-app import ~/interviews --collection Entrevistas` runs and then `echo-app bundle --collection entrevistas --out all.zip`
- **THEN** the recordings are in Entrevistas and `all.zip` holds one note for each that has a transcript

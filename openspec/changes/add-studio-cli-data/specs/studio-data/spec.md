## ADDED Requirements

### Requirement: Minutes from the command line
`echo-app meetings` SHALL list the recordings that have minutes, newest first, filtered by
`--since` and `--until` (a date, `today` or `yesterday`). `echo-app minutes ID` SHALL print a
recording's summary and its action items that are not discarded; `echo-app actions` SHALL print
the action items across recordings, filtered by date and owner. With `--json` each SHALL print
the recording as `info --json` does, with the minutes and, for each item, its text, owner, due
date, time, context, whether the user edited or added it, and what was said around its time.
JSON keys SHALL only be added, never renamed or removed. These commands SHALL send nothing.

#### Scenario: A nightly sync
- **WHEN** a script runs `echo-app actions --since today --json` after a day with two meetings
- **THEN** it gets every item the user kept, as edited, with its context and quote, and the
  discarded ones are not there

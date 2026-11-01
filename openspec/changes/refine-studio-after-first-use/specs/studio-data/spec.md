## MODIFIED Requirements

### Requirement: Minutes from the command line
`echo-app meetings` SHALL list the recordings that have minutes, newest first, filtered by
`--since` and `--until` (a date, `today` or `yesterday`), and by `--starred` to the starred ones.
`echo-app minutes ID` SHALL print a recording's summary and its action items that are not
discarded, each with its description and context but never the user's note. `echo-app actions`
SHALL print the action items across recordings, filtered by date and owner.

With `--json` each SHALL print the recording as `info --json` does, with the minutes, whether it is
starred, and for each item:
- its text, description, owner, due date and time;
- the user's context and note;
- whether the user edited or added it;
- what was said around its time.

#### Scenario: Today's items for the tracker
- **WHEN** an agent runs `echo-app minutes ID --json` for this morning's sync
- **THEN** each item has its description, the user's context and a quote, and the agent keeps the note out of the tracker

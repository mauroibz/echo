## ADDED Requirements

### Requirement: Action items from the summary
After a recording is summarized, Studio SHALL save its action items in `actions.json` in the
recording's folder, each with its text, owner, due date, the time in the audio where it came up
when known, and a done flag. Summarizing again SHALL keep the done flag of an item whose text is
unchanged. A failure SHALL leave the summary saved.

#### Scenario: A summary with next steps
- **WHEN** a meeting where Lucía agreed to send the proposal on Friday is summarized
- **THEN** `actions.json` holds "Enviar la propuesta", owner Lucía, the Friday's date and the
  time it was said

### Requirement: Where action items show
The Summary view SHALL list the recording's items as checkboxes with a button that plays where
each came up. A Pending screen, opened beside People or with Ctrl+Shift+T, SHALL list the open
items of every recording, newest first, filtered by owner and by tag. A person's profile SHALL
list their open items. Checking an item anywhere SHALL save it.

#### Scenario: Catching up
- **WHEN** the user opens Pending, picks Lucía and presses an item's time
- **THEN** the recording opens and plays from where the item came up

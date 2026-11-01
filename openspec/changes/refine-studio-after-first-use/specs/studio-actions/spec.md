## MODIFIED Requirements

### Requirement: Action items from the summary
After a recording is summarized, Studio SHALL save its action items in `actions.json` in the
recording's folder. Each SHALL have:
- a title and an owner;
- a description of what exactly is to be done and why, with the details said about it;
- a due date;
- the time in the audio where it came up, when known.

Summarizing again SHALL keep, for an item the model gives again, the user's edits, context, note
and discard, and SHALL keep the items the user added. A failure SHALL leave the summary saved.

#### Scenario: A summary with next steps
- **WHEN** a meeting where Lucía agreed to send the proposal with the new price to Acme on Friday is summarized
- **THEN** `actions.json` holds "Enviar la propuesta", a description naming the new price and Acme, owner Lucía, the Friday's date and the time it was said

#### Scenario: Summarizing again keeps the user's work
- **WHEN** the user rewrote one item, discarded another, added a third and summarizes again
- **THEN** the rewritten item keeps its new text, the discarded one stays discarded and the
  added one is still there

### Requirement: Where action items show
The Minutes view SHALL list the recording's items in a column beside the summary, with their
count. Each item SHALL show its title, owner, due date as "by <date>", description, context, the
user's note and a button that plays where it came up.

A person's page SHALL list the items assigned to them across the library, newest first, and they
SHALL be polished there as in the Minutes view. Items SHALL NOT carry a done state, and no screen
SHALL mark items as late or pending.

#### Scenario: From a profile to the moment
- **WHEN** the user opens Lucía's page and presses an item's time
- **THEN** the recording opens and plays from where the item came up

#### Scenario: After summarizing again
- **WHEN** the user presses Summarize again while the Minutes view is shown
- **THEN** once it is done the items are listed in full, not as an empty strip

### Requirement: Polishing action items
The user SHALL be able to:
- edit an item's title, description, owner and due date;
- add context for whoever picks the item up, and a note for themselves;
- discard an item and restore a discarded one;
- add an item by hand in the Minutes view.

Each change SHALL be saved to the item's recording's `actions.json` at once.

#### Scenario: Ready for the tracker
- **WHEN** the user rewords "Revisar costos" to "Revisar costos del proveedor de pagos", adds
  "pedir la cotización a Tomás" as context and discards "Mandar la grabación"
- **THEN** the list shows the new text with its context, the discarded item is out of the list
  under "1 discarded", and both changes are in `actions.json`

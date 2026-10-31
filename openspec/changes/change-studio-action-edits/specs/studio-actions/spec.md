## MODIFIED Requirements

### Requirement: Action items from the summary
After a recording is summarized, Studio SHALL save its action items in `actions.json` in the
recording's folder, each with its text, owner, due date and the time in the audio where it came
up when known. Summarizing again SHALL keep, for an item the model gives again, the user's
edits, context and discard, and SHALL keep the items the user added. A failure SHALL leave the
summary saved.

#### Scenario: A summary with next steps
- **WHEN** a meeting where Lucía agreed to send the proposal on Friday is summarized
- **THEN** `actions.json` holds "Enviar la propuesta", owner Lucía, the Friday's date and the
  time it was said

#### Scenario: Summarizing again keeps the user's work
- **WHEN** the user rewrote one item, discarded another, added a third and summarizes again
- **THEN** the rewritten item keeps its new text, the discarded one stays discarded and the
  added one is still there

### Requirement: Where action items show
The Summary view SHALL list the recording's items that are not discarded, each with its owner,
its due date as "by <date>", its context and a button that plays where it came up. A person's
profile SHALL list the items assigned to them across the library, newest first. Items SHALL NOT
carry a done state, and no screen SHALL mark items as late or pending.

#### Scenario: From a profile to the moment
- **WHEN** the user opens Lucía's profile and presses an item's time
- **THEN** the recording opens and plays from where the item came up

## ADDED Requirements

### Requirement: Polishing action items
In the Summary view the user SHALL be able to edit an item's text, owner and due date, add a
line of context, discard it, restore a discarded item, and add an item by hand. Each change
SHALL be saved to `actions.json` at once.

#### Scenario: Ready for the tracker
- **WHEN** the user rewords "Revisar costos" to "Revisar costos del proveedor de pagos", adds
  "pedir la cotización a Tomás" as context and discards "Mandar la grabación"
- **THEN** the list shows the new text with its context, the discarded item is out of the list
  under "1 discarded", and both changes are in `actions.json`

## MODIFIED Requirements

### Requirement: Where action items show
A recording SHALL have an Action items view beside Transcript and Minutes, listing its items at
the width of the content; its tab SHALL show how many items are not done. Minutes SHALL show the
summary alone. Each item SHALL show a done checkbox, its title, owner, due date as "by <date>",
description, context, the user's note and a button that plays where it came up.

A person's page SHALL list the items assigned to them across the library, newest first, and they
SHALL be worked on there as in the Action items view. No screen SHALL mark items as late or
pending, and Echo SHALL NOT remind about them.

#### Scenario: A narrow window
- **WHEN** the window is 900 pixels wide and the user opens a meeting's Action items
- **THEN** the items take the content's width, beside the recordings list, with no summary beside them

#### Scenario: Checked off
- **WHEN** the user checks "Revisar el contrato marco"
- **THEN** it shows struck through on one line, `actions.json` has it done, and the tab counts one fewer

### Requirement: Sending action items to a tracker
Each item SHALL have a state (proposed, ready, sent or failed) and a uid that summarizing again
does not change.

Each item SHALL have a To tracker switch, off by default. Switching it on SHALL make the item
ready, switching it off SHALL make it proposed, and discarding it SHALL switch it off. Switching a
failed item on SHALL make it ready again.

An item marked sent SHALL keep the tracker's reference, link and time, show them, and SHALL NOT
be edited, discarded or switched in Echo afterwards; it SHALL still take the done mark. An item
marked failed SHALL show why.

Summarizing again SHALL keep ready, sent and failed items as they are, also when the model no
longer lists them. Echo SHALL NOT contact any tracker.

#### Scenario: Two of five go
- **WHEN** a meeting has five items and the user switches on two
- **THEN** `echo-app actions --ready` lists those two and no others

#### Scenario: One could not be sent
- **WHEN** the sender marks one item sent as PROJ-7 and another failed with "no project for this client"
- **THEN** the first shows "✓ Sent · PROJ-7" with its link, and the second says "Could not be sent: no project for this client" with its switch off

### Requirement: Processed meetings
The user SHALL be able to mark a meeting reviewed and take it back. A meeting SHALL be processed
when it is reviewed and no item is ready or failed; a meeting with nothing switched on SHALL be
processed once reviewed. The Action items view and the meeting's card on the Briefing SHALL say
so. The open Action items view SHALL follow changes written by others within a few seconds.

#### Scenario: Ready to archive
- **WHEN** the meeting is reviewed and its last ready item is marked sent while its Action items are open
- **THEN** within seconds the view says "✓ Processed" and its Briefing card shows "✓ Processed"

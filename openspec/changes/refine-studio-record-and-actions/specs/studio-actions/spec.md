## MODIFIED Requirements

### Requirement: Where action items show
A recording SHALL have an Action items view beside Transcript and Minutes, listing its items at
the width of the content; its tab SHALL show how many items are not done. Minutes SHALL show the
summary alone. Each item SHALL show a done checkbox, its title, owner, due date as "by <date>",
description, context, the user's note and a button that plays where it came up.

Done items SHALL move to the end of a list, folded under one line ("N done") that shows them.
After an item is checked off or discarded, or a meeting's items are all switched, the list SHALL
offer to undo it for a few seconds (also with Ctrl+Z). The lists SHALL work from the keyboard:
↑/↓ (or J/K) to move, Space to check off, T to switch for the tracker, E or Enter to edit, Delete
to discard or restore.

A person's page SHALL list the items assigned to them across the library, newest first, and they
SHALL be worked on there as in the Action items view. The rail's Action items page SHALL list
every item not done nor discarded across the library, newest meeting first, in a card per meeting
that shows its date, people and how many items are done and opens its Action items; each item
SHALL show its owner, due date, moment and tracker state at a glance. The page SHALL count open
items, items to send, items in the tracker and items without an owner, each count filtering the
list, and SHALL filter by owner and by the item's words, owner, description and meeting title;
an item checked off or discarded there SHALL leave the page. No screen SHALL mark items as late or
pending, and Echo SHALL NOT remind about them.

#### Scenario: A narrow window
- **WHEN** the window is 900 pixels wide and the user opens a meeting's Action items
- **THEN** the items take the content's width, beside the recordings list, with no summary beside them

#### Scenario: Checked off
- **WHEN** the user checks "Revisar el contrato marco"
- **THEN** it moves under "1 done" at the end, `actions.json` has it done, the tab counts one fewer, and Undo takes it back

#### Scenario: Last week's items
- **WHEN** three meetings have open items and the user opens Action items in the rail and types "lucía"
- **THEN** the page shows the open items Lucía owns, under the heading of each meeting they came from

### Requirement: Sending action items to a tracker
Each item SHALL have a state (proposed, ready, sent or failed) and a uid that summarizing again
does not change.

Each item SHALL have a To tracker switch, off by default. Switching it on SHALL make the item
ready, switching it off SHALL make it proposed, and discarding it SHALL switch it off. Switching a
failed item on SHALL make it ready again. Switch all on SHALL switch on every item of the meeting
that is not done, discarded or sent (Switch all off, every one of those off).

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
The user SHALL be able to say they are done with a meeting ("Done with this meeting") and take it
back. Each control of the Action items view SHALL say what it does in its tooltip; the view SHALL
NOT carry a paragraph of instructions. A meeting SHALL be processed
when the user is done with it and no item is ready or failed; a meeting with nothing switched on SHALL be
processed once the user is done with it. The Action items view and the meeting's card on the Briefing SHALL say
so. The open Action items view SHALL follow changes written by others within a few seconds.

#### Scenario: Ready to archive
- **WHEN** the user is done with the meeting and its last ready item is marked sent while its Action items are open
- **THEN** within seconds the view says "✓ Processed" and its Briefing card shows "✓ Processed"

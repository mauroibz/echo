## ADDED Requirements

### Requirement: Sending action items to a tracker
Each item SHALL have a state (proposed, ready, sent or failed) and a uid that summarizing again
does not change.

Marking a meeting ready SHALL make every item that is not discarded and not sent ready, after
listing those items for the user to confirm. Taking it back SHALL return the ready items to
proposed.

An item marked sent SHALL keep the tracker's reference, link and time, show them, and SHALL NOT
be edited or discarded in Echo afterwards. An item marked failed SHALL show why, and marking the
meeting ready again SHALL make it ready.

Summarizing again SHALL keep ready, sent and failed items as they are, also when the model no
longer lists them. Echo SHALL NOT contact any tracker.

#### Scenario: Approving yesterday's sync
- **WHEN** the user discarded one of five items and presses Ready to send…
- **THEN** Echo lists the four that will go, and after Mark ready the four show "Ready"

#### Scenario: One could not be sent
- **WHEN** the sender marks three items sent as PROJ-7 to PROJ-9 and one failed with "no project for this client"
- **THEN** the three show "✓ Sent · PROJ-…" with their links, and the fourth says "Could not be sent: no project for this client"

### Requirement: Processed meetings
A meeting SHALL be processed when it was marked ready and every item that is not discarded is
sent; a meeting without items SHALL be processed once marked. The minutes view and the meeting's
card on the Briefing SHALL say so. The open minutes view SHALL follow changes written by others
within a few seconds.

#### Scenario: Ready to archive
- **WHEN** the last ready item of a meeting is marked sent while its minutes are open
- **THEN** within seconds the view says "✓ Processed" and that the call can be archived, and its Briefing card shows "✓ Processed"

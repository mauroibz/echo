## ADDED Requirements

### Requirement: Bundle of recordings
The user SHALL be able to bundle the selected recordings (one, several, or a linked set as its
parts) from the list's menu, the bar under a selection of several, the header's Export button and
Ctrl+Shift+B: a dialog lists the parts at least one of them has (the transcript, and those
extensions offer), each to tick, with an option to start each passage with its time, and either
copies the result to the clipboard or saves it as a zip. The bundle SHALL be Markdown with one
note per recording, oldest first for several, each with its title, date, length, tags, people and
notes and the ticked parts under a heading each, the transcript last and with speakers' names;
the zip SHALL hold one note per recording. A recording with none of the ticked parts SHALL be
left out. The ticks SHALL be remembered, Copy SHALL be the default button, and the message
afterwards SHALL say how many recordings and about how many words went.

#### Scenario: Three meetings to an assistant
- **WHEN** the user selects three meetings, presses Ctrl+Shift+B, unticks Transcript and presses Enter
- **THEN** the clipboard holds three notes, oldest first, each with its summary and action items, and the next bundle opens with Transcript unticked

#### Scenario: Nothing to bundle
- **WHEN** the user bundles a recording that has no transcript and no other part
- **THEN** no dialog opens and a message says there is nothing to bundle yet

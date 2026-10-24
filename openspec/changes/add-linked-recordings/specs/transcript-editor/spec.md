## ADDED Requirements

### Requirement: A set's transcript
Selecting a set SHALL show its parts' transcripts one under the other in set order, each under
a heading with the part's title, date and length. The text SHALL be editable in place, each
part's edits SHALL be saved to that part only, and no edit SHALL move text across a heading.
Find, copy, passage times, follow-along, low-confidence shading and playing the passage at the
cursor SHALL work across the whole set. Parts without a transcript SHALL show their state under
their heading. Exports of a set SHALL contain every part, with times on the set's timeline.

#### Scenario: Editing the second part
- **WHEN** the user corrects a word in the second part of a set
- **THEN** only the second recording's edited transcript changes, and selecting that part alone shows the correction

#### Scenario: Deleting across a heading
- **WHEN** the user selects text from the end of the first part to the start of the second and presses Delete
- **THEN** nothing is deleted and the parts stay separate

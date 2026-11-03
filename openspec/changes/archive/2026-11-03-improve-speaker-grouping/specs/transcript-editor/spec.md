## ADDED Requirements

### Requirement: One speaker per person
After a recording's speakers are labeled, Echo SHALL join, as merges the user can separate again,
speakers that sound like the same known person, speakers on different tracks of a call whose
voices are at least 0.82 similar, and speakers with under 1.5% of the speech (and under a minute),
which join the nearest voice. It SHALL never join speakers the user named differently. Recordings
labeled before SHALL be grouped once, when first shown, and not again after the user separates
them unless the user asks: "Group speakers again" SHALL group the recording with the voices
known then.

A speaker SHALL be suggested as a known person from 0.75 similarity with a lead of 0.1 over
everyone else, by the voices as they are now, and SHALL be named without asking from 0.85 with a
lead of 0.2 when that voice was learned from at least two recordings; such a name SHALL NOT teach
the voice.

#### Scenario: A call without headphones
- **WHEN** a 3-person call is labeled with each voice on both tracks and two short fragments
- **THEN** the recording shows 3 speakers, and "Separate again" on one restores its parts

#### Scenario: Someone Echo knows well
- **WHEN** Lucía's voice was learned from three recordings and a new speaker sounds 0.9 like her and 0.4 like anyone else
- **THEN** the speaker is named Lucía without the bar asking, and her voice does not change

### Requirement: Choosing a known person
The naming bar SHALL offer, beside the name field, a list of the meeting's invitees (from an
extension), the known voices the speaker sounds closest to, and everyone named before; choosing
one SHALL name the speaker. Naming a speaker with a name another speaker of the recording has
SHALL make them one speaker.

#### Scenario: Picked from the list
- **WHEN** the bar asks about speaker 3 and the user opens the list and chooses "Tomás"
- **THEN** speaker 3 is named Tomás

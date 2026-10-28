## ADDED Requirements

### Requirement: Speaker changes in a call
In a recorded call, a passage SHALL be cut where the track other than its main one speaks for at
least a second, without the segmentation model, and where someone other than the main voice of
the computer audio speaks for at least a second, by the segmentation model run on the computer
audio alone. A piece cut out where the other track speaks SHALL be labeled from that track. A
call whose two tracks hold the same sound SHALL be labeled like a recording from one microphone.

#### Scenario: Someone on the call cuts in
- **WHEN** the user talks for a minute and a person on the call says "¿y eso cuándo?" over them for a second and a half
- **THEN** those words are a passage of their own, labeled as that person and not as the user

#### Scenario: Two people on the call
- **WHEN** one person on the call answers another inside what the planner made one passage
- **THEN** the answer is a passage of its own with the second person's label

#### Scenario: Both tracks recorded the microphone
- **WHEN** a call was recorded with the same sound on both tracks
- **THEN** it is transcribed and labeled as from one microphone, with no cuts from the tracks

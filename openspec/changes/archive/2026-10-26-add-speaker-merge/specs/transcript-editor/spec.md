## ADDED Requirements

### Requirement: Merging speakers
The user SHALL be able to declare, from a speaker's label, that the speaker is the same person
as another speaker of the recording, and to separate them again. A merged speaker SHALL keep the
other speaker's number and name, or take this one's name when the other had none, and SHALL be
treated as one speaker everywhere: labels, the naming bar, the speaker count, exports, search by
speaker and people's recordings. Naming a merged speaker SHALL remember the voice of all its
parts. Merges SHALL be stored apart from the model's transcript and SHALL be dropped when the
recording is transcribed again.

#### Scenario: One person found twice
- **WHEN** speakers 2 and 3 are the same person and the user chooses "Same person as → Speaker 2" on speaker 3
- **THEN** the margin shows one speaker where 3 was, the status counts one fewer speaker, naming speaker 2 "Ana" names every passage of both, and the TXT export prefixes all of them with "Ana"

#### Scenario: Separate again
- **WHEN** the user chooses "Separate again" on the merged speaker
- **THEN** speaker 3 is labeled on its own again, unnamed

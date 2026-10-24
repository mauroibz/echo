## ADDED Requirements

### Requirement: Linked sets
Recordings SHALL be linkable into ordered sets stored as one JSON file per set in the data
folder's `sets/` directory, holding the set's id, title and member ids in order. Linking,
reordering and unlinking SHALL NOT change any member's folder. A recording SHALL belong to at
most one set; a member that is missing SHALL be skipped and SHALL rejoin the set if it comes
back; a set with fewer than two present members SHALL be shown as its remaining recording.

#### Scenario: Restoring a deleted part
- **WHEN** the user deletes the second of three linked voice notes and later restores it from the trash
- **THEN** the set shows two parts while it is deleted and three parts in the original order after it is restored

#### Scenario: Linking a member of another set
- **WHEN** the user links a recording that belongs to set A into set B
- **THEN** it is a member of set B only and set A no longer lists it

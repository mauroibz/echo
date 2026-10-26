## ADDED Requirements

### Requirement: Profiles are files
A person's notes and tags SHALL be kept in one JSON file per person in the data folder's
`people/` folder, written atomically, and the search index SHALL be rebuildable from them. A
recording SHALL match a tag in search when it carries the tag or when a person who speaks in it
carries it.

#### Scenario: A person's tag finds their calls
- **WHEN** Ana is tagged `client:Acme` and speaks in two untagged calls
- **THEN** searching `#client:acme` lists both calls

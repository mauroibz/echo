## MODIFIED Requirements

### Requirement: Profiles are files
A person's notes, tags and email SHALL be kept in one JSON file per person in the data folder's
`people/` folder, written atomically, and the search index SHALL be rebuildable from them. An
email SHALL be stored lower case and SHALL belong to one person. A recording SHALL match a tag in
search when it carries the tag or when a person who speaks in it carries it.

#### Scenario: A person's tag finds their calls
- **WHEN** Ana is tagged `client:Acme` and speaks in two untagged calls
- **THEN** searching `#client:acme` lists both calls

#### Scenario: An email finds the person
- **WHEN** Ana's profile has `ana@acme.example` and an extension looks up "Ana <ANA@acme.example>"
- **THEN** it gets Ana's profile

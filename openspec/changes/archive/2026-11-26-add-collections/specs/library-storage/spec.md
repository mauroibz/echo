## ADDED Requirements

### Requirement: Collections are in the recordings
A recording's collection SHALL be a field of its `meta.json`, empty for none, and nothing else
SHALL record collections: a collection exists while a recording names it. A recording written
before collections SHALL read as in none.

#### Scenario: The data folder is copied
- **WHEN** the recordings folder is copied to another computer and Echo starts there
- **THEN** the same collections hold the same recordings

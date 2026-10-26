## ADDED Requirements

### Requirement: Tag categories
A tag of the form `category:value`, with text on both sides of its first colon, SHALL belong to
that category; any other tag is a plain tag. Tags SHALL stay as typed in `meta.json`. Searching
`#category:value` SHALL find recordings with that tag, and `#category:` SHALL find recordings
with any tag of that category, compared without case or accents like every tag.

#### Scenario: Any client
- **WHEN** one recording is tagged `client:Acme`, another `Client:Globex` and a third `nota`
- **THEN** searching `#client:` finds the first two, and `#client:acme` only the first

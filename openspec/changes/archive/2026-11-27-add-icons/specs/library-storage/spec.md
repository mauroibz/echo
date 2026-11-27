## ADDED Requirements

### Requirement: Icons are plain data
A recording's icon SHALL be the `icon` field of its `meta.json` (`symbol` or `symbol:color`, empty
for none). Collections' icons SHALL be in `collections.json` in the data folder, by folded name;
that file SHALL hold nothing a collection's membership depends on, and an unreadable one SHALL
mean no icons.

#### Scenario: The icons file is lost
- **WHEN** `collections.json` is deleted
- **THEN** every collection still holds its recordings, with the folder icon

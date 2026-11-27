## ADDED Requirements

### Requirement: Subfolders of watched folders as collections
With the setting on, Echo SHALL also import new files from each folder directly inside a watched
folder (not deeper, not hidden ones) into a collection named after that folder, joining an existing
collection of that name. With it off, the default, subfolders SHALL NOT be looked at.

#### Scenario: A batch copied into a subfolder
- **WHEN** the user makes "Curso de ventas" inside a watched folder and copies 10 recordings into it
- **THEN** the 10 are imported into the collection Curso de ventas and none appears in the day-to-day list

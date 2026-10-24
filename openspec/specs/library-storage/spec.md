# library-storage Specification

## Purpose
Defines where and how Echo stores recordings, their metadata and transcripts so that the
files on disk are always the source of truth and nothing the user created is lost.

## Requirements

### Requirement: Data directory
Echo SHALL store all user data under a single data directory, defaulting to
`$XDG_DATA_HOME/echo` (or `~/.local/share/echo`), configurable in settings.

#### Scenario: Default location
- **WHEN** Echo starts with no settings file and `XDG_DATA_HOME` unset
- **THEN** it creates and uses `~/.local/share/echo`

### Requirement: One folder per recording
Each recording SHALL be a folder holding its audio, a `meta.json` with title, source, creation
time, duration, hash, crop, gaps, markers, tags and notes, and its transcripts. Everything the
index knows SHALL be derivable from these files.

#### Scenario: Tags survive a rescan
- **WHEN** the index is deleted and `echo-app rescan` runs
- **THEN** every recording's tags and notes are searchable again

### Requirement: Originals are never altered
Echo SHALL NOT modify or delete an original audio file except when the user deletes the
recording. Crop SHALL be stored as in and out points, and exporting a cropped version SHALL
write a new file.

#### Scenario: Crop does not touch audio
- **WHEN** the user sets crop points on a recording
- **THEN** the original audio file's bytes and hash are unchanged

### Requirement: Rebuildable index
Echo SHALL keep a searchable index of recordings that can be rebuilt entirely from the
recording folders. Deleting the index SHALL lose no user data.

#### Scenario: Index deleted
- **WHEN** the index file is deleted and `echo-app rescan` runs (or the app starts)
- **THEN** every recording folder appears in the library again with its title and
  transcript status

### Requirement: Deletion is recoverable
Deleting a recording SHALL move its folder to the desktop trash when available, or to a
`trash/` folder in the data directory otherwise.

#### Scenario: Delete then restore
- **WHEN** the user deletes a recording
- **THEN** its folder can be restored from the trash with all files intact

### Requirement: Settings
Settings SHALL be stored in one human-readable file in `$XDG_CONFIG_HOME/echo/`. Every
setting SHALL have a default, unknown keys SHALL be ignored, and an unreadable settings file
SHALL be reported and replaced by defaults without crashing.

#### Scenario: Corrupt settings
- **WHEN** the settings file contains invalid syntax
- **THEN** Echo starts with defaults, keeps the bad file as a backup, and reports it once

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

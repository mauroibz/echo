# Proposal

## Why

Interviews, meetings and diary notes end up in one flat, date-ordered list. A little structure
lets a library of hundreds of recordings stay navigable without folders or a database the user
has to think about.

## What Changes

- Free-form tags on recordings, stored in `meta.json`, indexed in SQLite, shown as chips above
  the list; clicking a chip filters, and search accepts `#tag`.
- A notes field per recording (plain text in `meta.json`), searchable.
- Grouping of the list by month, with per-recording word count, speaking rate and silence
  share shown in the detail header.

## Capabilities

### Modified Capabilities
- `library-storage`: tags and notes in `meta.json`, indexed.
- `desktop-app`: tag chips, filters, month grouping, statistics.

## Impact

`library.py`, `index.py` (schema version bump and rescan), `ui/library_view.py`,
`ui/main_window.py`, `ui/player.py` (header), `cli.py` (`list --tag`, `tag ID add|remove`).

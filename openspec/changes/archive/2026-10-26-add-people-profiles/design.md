# Design

## Decisions

### Profiles in the data folder, one file each

Notes and tags about a person are the user's content, like a recording's notes, so they live in
the data folder (`people/<slug>.json`: name, notes, tags), not with the settings: they are backed
up and synced with the recordings they describe. One file per person keeps two machines editing
different people from conflicting. The slug is the folded name with anything but letters, digits
and `-` replaced; the name inside the file is the truth. Aliases stay in the dictionary, where
transcription reads them, and voices stay in `voices.json`; the profile shows and edits both.

### Who is a person

Everyone in the dictionary's people, everyone with a profile file and every name given to a
speaker (from the index's `speakers` table, added by `add-speaker-search`). Nothing is created
until the user writes something: opening a profile does not write a file.

### Tags reach their recordings in search

A tag filter matches recordings with the tag or with a speaker who has it. Tagging every
recording of a client is the chore categories were meant to ease; tagging the client's people
once does it for every later call too. The index gets a `person_tags(name_folded, tag_folded)`
table from the profile files.

### The voice sample

The latest recording the person speaks in, their longest passage there, 6 s, played by a
`Playback` of the dialog's own (two-track recordings mixed), so the main player is untouched.

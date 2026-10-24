# Design

## Decisions

- **Data.** `Meta` gains `tags: list[str]` and `notes: str = ""`. Tags are stored as typed
  but compared folded (lowercase, accents removed, as the search tokenizer does); a tag is 1
  to 32 characters without `#`, commas or newlines. `Recording.update(tags=…)` validates.
- **Index.** `SCHEMA_VERSION = 2`: table `tags (id TEXT, tag TEXT, tag_folded TEXT)` with an
  index on `tag_folded`; `notes` is added to the FTS `body` (title, notes, transcript text
  concatenated with newlines). The version bump drops and rebuilds on first open, as the
  module already does.
- **Search syntax.** Tokens starting with `#` in the search box filter by tag (AND); the rest
  is full-text as today. `Index.list(query, tags=[...])` joins on the tags table.
- **Chips.** A `TagBar` flow-layout widget between the search box and the list showing the
  distinct tags with counts, most used first, up to 12 plus "more…" as a menu. Clicking
  toggles the chip and adds or removes `#tag` in the search box, so the box stays the single
  source of the filter.
- **Editing.** In the player header under the title: a `TagEditor` (chips with × and an inline
  "+ tag" entry with completion from existing tags) and a one-line "Notes" field that expands
  to three lines on focus; both autosave on change like the title does.
- **Grouping.** `LibraryModel` inserts month header rows ("Octubre 2025") when the list has
  more than 30 recordings or spans more than two months; the delegate draws them as
  non-selectable section headers. Sort stays newest first.
- **Statistics.** Shown under the duration in the header: words (from `rec.text()`), words
  per minute of speech, and silence share, both from the transcript's segments (speech
  seconds = sum of segment durations). No transcript → only duration.
- **CLI.** `echo-app list [--tag T]...` and `echo-app tag ID [+tag ...] [-tag ...]`.

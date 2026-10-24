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

## Decisions made while implementing

- **Month names in English** ("October 2026"), like the rest of the interface ("Today",
  "Yesterday"); the design's example was Spanish.
- **Chip counts come from the list model**, which already holds every recording's metadata, so
  the bar updates as soon as a tag is edited without waiting for the index. Tags spelled
  differently are counted together and shown as most often typed.
- **Tag editor**: Enter adds (a leading `#` is dropped), the chip's × removes, completion
  offers tags from the whole library. Tags are cleaned on save: no `#`, commas or line
  breaks, at most 32 characters, one per folded spelling.
- **Notes**: a plain-text field, one line at rest and three while editing, saved when focus
  leaves it.
- **Headings** are rows of the list model with no item flags, so they cannot be selected or
  reached with the arrow keys; selection helpers skip them (`first_row`, `nearest_row`).
- **Statistics** count words in the shown text over the transcript's passage time; silence is
  the share of the (cropped) span outside passages. They are a second line of the header.
- **`echo-app tag ID +a -b`** takes its changes after the id (so `-b` is not read as an option).

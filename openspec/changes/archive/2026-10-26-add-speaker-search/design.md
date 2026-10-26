# Design

## Decisions

### What a speaker said, indexed per speaker

A second full-text table, `spoken(id, person, body)`, holds one row per named speaker per
recording: the text of their passages, from the shown text (the edited text when there is one,
mapped to passages with `align.cues`, as exports do). A `speakers(id, name, name_folded,
seconds)` table lists who speaks where. Both are rebuilt with the rest of the index and come
from the recording's files, so the index stays a cache; the schema version goes up, which
rebuilds it on first start.

### Names in queries

`@token` folds the token, splits it at `_`, and matches a speaker whose folded name has those
words in a row, each matched from its start (`@ana` matches "Ana López", `@lop` too, `@ana_lo`
too). This is done in Python over the few names in `speakers`, then turned into a set of exact
names for SQL; matching names in SQL would need a tokenizer for names alone.

### Snippets

With words and `@`, results come from `spoken` with FTS5's `snippet()`, about twelve words
around the first match, prefixed with the speaker's name. The list row grows a third line only
when it has a snippet, so ordinary searches look as before.

### Finding in the transcript

The window passes the matching speaker numbers with the words; the transcript's find keeps only
matches inside passages of those speakers.

# Design

Decided with the user before building: a recording is in one collection at most; a collection's
recordings are summarized automatically like any other; a watched folder's subfolders can be
collections.

- **A field, not a file.** `collection` in `meta.json`. A collection exists while a recording names
  it: no empty collections, nothing to reconcile, no index column. See Collections in `docs/design.md`.
- **A scope beside the search filter** in the list model. Search ignores the scope; selecting a
  recording from elsewhere moves it.
- **Ask from two files up**, never with a collection open.
- **The bar is hidden without collections**, so Echo without them is unchanged.

## Decisions made while implementing

- Subfolder collections are a setting, off by default, and one level deep: existing watched folders
  (phone syncs) have subfolders that were never looked at, and turning them into imports and
  collections unasked would flood a library.
- A file already in the library is not moved by importing it again into a collection.
- A recording made while a collection is open goes to the day-to-day list; it shows while it records.
- Studio's People page and `echo-app meetings` / `actions` still cover every recording: they answer
  "who" and "what did we agree", which cut across collections as search does.
- The Markdown vault export is unchanged (no subfolder per collection); the Bundle zip is the way
  to take a collection out as files.

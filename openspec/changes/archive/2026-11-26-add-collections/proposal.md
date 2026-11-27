# Collections: a batch of recordings kept apart

## Why

The library is one list by date. With dozens of recordings a week, a batch dropped in together (a
round of interviews, a course) buries the day's meetings and is itself scattered among them. Tags
group but do not take anything out of the list, and a linked set is one conversation, not a folder.

## What Changes

- A recording can be filed in one collection; the list shows the day-to-day recordings or one
  collection, chosen in a bar above it. Search looks everywhere.
- Dropping or choosing two or more files asks for a collection; with one open they go into it.
- Move to collection (menu, drag), and Bundle, Rename and "Move all back" on a collection.
- `echo-app collections`, `--collection` on `import`, `list` and `bundle`, `collection` in JSON.
- Watched folders: optionally, each subfolder is a collection.
- Echo Studio: collections are summarized as usual but stay out of the Briefing, the Action items
  page and calendar matching.

## Capabilities

### Modified Capabilities

- `desktop-app`, `command-line`, `library-storage`, `audio-import`

## Impact

`src/echo_app/collections.py`, `ui/collections.py`, `ui/window_collections.py` (new); `library.py`,
`importer.py`, `watch.py`, `settings.py`, `cli.py`, `cli_rec.py`, `cli_json.py`, `ui/library_view.py`,
`ui/main_window.py`, `ui/window_library.py`, `ui/window_search.py`, `ui/watch.py`, `ui/dialogs.py`;
`src/echo_studio/home.py`, `actions.py`, `calendar.py`; `tests/test_collections.py`, `tests/test_ui.py`;
`docs/guide.md`, `docs/design.md`, `README.md`, `CHANGELOG.md`, `agents/echo/SKILL.md`. No new dependency.

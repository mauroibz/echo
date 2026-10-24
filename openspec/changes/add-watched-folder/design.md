# Design

## Decisions

- **Settings lists.** `settings.py` only serializes bool, int and str. Add list-of-str support
  in `_toml_value` (a TOML array of quoted strings) and in `load` (accept a list whose items
  are all str). Setting: `watch_dirs: list[str] = []`.
- **Stability.** A file is imported when its size has not changed for 3 seconds and it is
  not locked for writing (opening for append succeeds). Checked by the watcher, not the
  importer, so the importer API is unchanged.
- **Ledger.** `<data>/watch.json`: `{"<folder>": {"<sha256>": "<recording id>", "failed":
  {"<path>": "<reason>"}}}`. A file whose hash is in the ledger or already in the library is
  skipped silently; a failed file is retried only when its size or mtime changes.
- **Watching.** `ui/watch.py`: `QFileSystemWatcher` on each folder (directory-level, not
  recursive; the settings page says so), a 2-second debounce after a change, and a full scan
  of each folder on start and every 5 minutes as a safety net. Imports run in the existing
  background thread used by drag-and-drop and show the same status-bar summary. Transcription
  is queued through the existing auto-transcribe path.
- **Headless.** `echo-app import --watch` runs the same scanner in a loop with `--interval`
  (default 30 s), using `os.scandir` polling instead of Qt, for a server-like setup.
- **UI.** Settings → "Watched folders": a list with Add (folder dialog) and Remove.

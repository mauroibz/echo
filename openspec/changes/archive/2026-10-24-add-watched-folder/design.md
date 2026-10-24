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

## Decisions made while implementing

- **Ledger layout**: `{"<folder>": {"handled": {"<path>": [size, mtime_ns]}, "failed": {"<path>":
  {"signature": [size, mtime_ns], "reason": "..."}}}}` rather than hashes as keys: a file whose
  size and modification time are unchanged is skipped without hashing it again, which matters
  for folders full of long recordings. Duplicates (by hash) are still detected by the importer.
- **"Not locked for writing"** is checked only on Windows, where a file being written cannot be
  opened by another process. POSIX has no such lock, and synced folders may be read-only, so
  there the size and time staying the same for 3 seconds is the test.
- **Scanner** (`watch.py`, stdlib) is shared by the window and the CLI; the window runs it on
  the background thread, one scan at a time, and looks again 3.5 s later while files are still
  settling.
- **Settings**: lists of strings are now allowed in `settings.toml` (`watch_dirs`), and Settings
  has an "Import" tab with the folders, Add and Remove.
- **`echo-app import --watch`** takes folders or uses the ones in settings, polls every
  `--interval` seconds (30 by default) and sooner while a file is settling, and stops on Ctrl+C.

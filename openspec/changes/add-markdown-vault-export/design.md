# Design

## Decisions

- **Note format** (`export.to_markdown(rec, opts)`):

  ```markdown
  # <title>

  _<YYYY-MM-DD HH:MM>_ · <duration> · #tag1 #tag2
  People: Lucía Fernández, Mauro        (dictionary people found in the text; speakers once labeled)
  Audio: [audio.flac](<relative path>)

  ## 00:00 <first marker note or "Inicio">
  <paragraphs; with timestamps on, each paragraph starts with `[m:ss]`>

  ## 10:12 <marker note>
  ...
  ```

  Without markers there is one body with no `##` headings. Options: timestamps on/off,
  audio copy/link/none.
- **Folder export.** `export.export_folder(lib, recs, dest, opts)`: one file per recording
  named `<YYYY-MM-DD> <title>.md` (sanitized as `suggested_name` does, de-duplicated with a
  numeric suffix), audio in `<dest>/audio/<id>.<ext>` when copying. A ledger `<dest>/
  .echo-export.json` maps recording id to the sha256 of the rendered note and the audio, so
  unchanged notes are skipped and renamed recordings replace their old file.
- **Sync.** Settings `export_dir: str = ""` and `export_sync: bool = False`. When sync is on,
  the window re-exports a recording whenever its transcript, edits, title, tags, markers or
  notes change (the library's existing change notifications), debounced 2 seconds, in the
  background thread. Off by default; the Settings page explains it writes files outside Echo.
- **UI and CLI.** File → "Export library to folder…" (selection or all); `echo-app export
  --all DIR [--audio copy|link|none] [--timestamps]`.
- **Docs.** `docs/sync.md`: the data folder is plain files; sync it with Syncthing or a
  mounted drive; `data_dir` can point at the synced copy; two machines must not record into
  the same folder at once (the recording lock is per machine); run `echo-app rescan` after a
  sync tool restores files; the SQLite file should be excluded from sync.

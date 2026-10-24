# Proposal

## Why

Transcripts are most useful next to the user's other notes. Echo's files are already plain, so
a good Markdown export and clear guidance on syncing the data folder cover most of what a
"sync" feature would, with none of the machinery.

## What Changes

- Richer Markdown export: title and date, tags, people from the dictionary and speakers as a
  header, markers as headings, paragraphs with optional timestamps, and a relative link to the
  audio file.
- Export a selection or the whole library to a folder, one `.md` per recording (with the audio
  copied or linked), skipping files that are up to date. Optionally kept in sync: the folder
  is rewritten whenever a transcript changes.
- A `docs/sync.md` page: syncing the data folder with Syncthing or a mounted drive, the
  `data_dir` setting, and what `echo-app rescan` does.

## Capabilities

### Modified Capabilities
- `transcript-editor`: Markdown export content; library export to a folder.

## Impact

`export.py`, `ui/main_window.py` (Export library…), `settings.py` (`export_dir`,
`export_sync`), `cli.py` (`echo-app export --all DIR`), docs.

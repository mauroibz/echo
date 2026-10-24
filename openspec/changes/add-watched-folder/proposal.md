# Proposal

## Why

Voice notes arrive from a phone through a sync folder or a WhatsApp export. Importing them by
hand is the kind of chore that makes a library fall behind.

## What Changes

- Settings → Import: one or more watched folders. New audio files appearing there are imported
  with the existing importer (duplicates skipped, WhatsApp dates recognized) and queued for
  transcription when auto-transcribe is on.
- Watching runs in the window process with `QFileSystemWatcher`, plus a scan on start; files
  are imported only once they stop growing for a few seconds. Originals are left in place.
- `echo-app import --watch` for a headless setup.

## Capabilities

### Modified Capabilities
- `audio-import`: watched folders.

## Impact

`importer.py` (stability check), new `ui/watch.py`, `settings.py` (`watch_dirs`), `cli.py`.

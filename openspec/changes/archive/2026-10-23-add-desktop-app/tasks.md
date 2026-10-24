# Tasks

## 1. Shell

- [x] 1.1 App bootstrap: QApplication, single instance with file forwarding, logging, recovery and index sync in background, ui.json persistence; verify a second launch focuses the first and forwards a file (test with QLocalSocket)
- [x] 1.2 Main window layout, menus with shortcuts, status bar, tray while recording, close-during-recording behavior; verify with an offscreen smoke test and screenshots in light and dark palettes

## 2. Library and recorder UI

- [x] 2.1 LibraryModel with incremental refresh, row delegate with live status chips, empty state, search via FTS, context menu, rename, delete to trash; verify model tests (refresh picks up progress and new folders)
- [x] 2.2 Drag and drop import with progress and summary; verify by simulating a drop event in a test
- [x] 2.3 Recorder panel: source combo, level meter widget, listen toggle, record/pause/stop, elapsed, warnings; verify by recording from the window offscreen with the fake capture command

## 3. Player and editor

- [x] 3.1 Waveform widget with background peaks, playhead, crop handles, snapping, keyboard nudging; verify peaks tests and a screenshot
- [x] 3.2 Player controls with ffmpeg piped into pw-play, speed, crop enforcement, export audio; verify export tests (cropped FLAC exact span, uncropped copy identical)
- [x] 3.3 Transcript panel: state views (none, queued, running, failed, models missing), editor with autosave, revert with confirmation, newer-model notice, copy, find, export, follow-along highlight, Ctrl+click seek; verify editor tests

## 4. First run, settings, setup check

- [x] 4.1 Welcome dialog with microphone meter and model download with progress; verify offscreen screenshot and that skipping leaves recording usable
- [x] 4.2 Settings dialog and Check setup dialog; verify settings round-trip test
- [x] 4.3 Full interactive pass on the real desktop: record, pause, stop, import a WhatsApp note, transcribe, edit, crop, export; capture screenshots for the record

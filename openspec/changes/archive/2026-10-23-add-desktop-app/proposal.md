# Proposal

## Why

The engine pieces work from the command line, but Echo is meant to be a desktop app someone
opens, records with, drops files on, and reads transcripts in, without knowing any of the
machinery. This change adds the window and everything needed for it to feel finished.

## What Changes

- Main window: recorder controls and library on the left; player with waveform and crop on the
  right, above the transcript editor.
- Library list with search over titles and transcripts, live status per recording
  (recording, queued, transcribing with time left, failed, recovered, edited), drag and drop
  import anywhere in the window, context menu, rename, recoverable delete.
- Player with waveform, seek, speed, non-destructive crop with handles, snapping to pauses,
  keyboard nudging, and export of the cropped audio.
- Transcript editor: autosaved edits, undo, find, copy, export, re-transcribe, revert to model
  output, current passage highlighted during playback, click a passage to seek.
- App shell: single instance (a second launch focuses the window and imports files it was
  given), first-run welcome with microphone check and model download, one-page settings,
  "Check setup" (doctor) dialog, keyboard shortcuts, tray indicator while recording, closing
  the window never stops a recording, silent recovery after crashes, persistent layout.

## Capabilities

### New Capabilities
- `desktop-app`: the window, library, import by drag and drop, app lifecycle, first run, settings.
- `playback-and-crop`: listening to recordings, the waveform, and non-destructive crop.
- `transcript-editor`: reading, editing, copying and exporting transcripts.

### Modified Capabilities

## Impact

New package `src/echo_app/ui/` (PySide6 widgets). No torch import in this process.

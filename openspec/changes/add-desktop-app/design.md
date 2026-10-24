# Design

## Context

Engine APIs exist and are stdlib-only: `recorder` (start/active/Session/recover_all),
`importer`, `transcription` (request/cancel/ensure_worker), `library`, `index`, `doctor`,
`audio.monitor` (LevelMonitor, Listener). PySide6-Essentials includes QtMultimedia with an
FFmpeg backend. See proposal.md for motivation and PLAN.md section 10 for the quality bar.

## Goals / Non-Goals

**Goals:** native look on KDE (system style, palette and icon theme), no custom theming, no
blocking work on the UI thread, every engine state visible.

**Non-Goals:** multiple windows, tabs, a plugin system, theme settings.

## Decisions

### Layout

```
┌──────────────────────┬──────────────────────────────────────────────┐
│ Source ▾   [listen]  │ Title (F2 to rename)        date · 12:34 · src │
│ ▓▓▓▓▓▓▓░░░░░  meter  │ ▁▃▅▇▅▃▁▂▅▇▇▅▂▁  waveform, crop handles      │
│ (●) Record  ❙❙  ■    │ ▶  03:21 / 12:34   1x ▾   [ ] crop  export    │
│ 00:12:34  warning    ├──────────────────────────────────────────────┤
│ [Search…          ]  │ Model transcript · adapter    Copy  Export  ⋯ │
│ ● Recording   12:34  │                                              │
│ Reunión…  ⟳ 45% 1m   │  Transcript text, editable, autosaved        │
│ Voice note   ✓       │                                              │
└──────────────────────┴──────────────────────────────────────────────┘
```

A horizontal `QSplitter` (left, right) and a vertical one (player, editor). Sizes persist in
`QSettings`-free form: a small JSON in the state dir (`ui.json`), to keep all persistence in our
own files.

### Model and refresh

`LibraryModel(QAbstractListModel)` holds `Recording` objects. A 1 s timer scans the recordings
directory (`os.scandir` + folder mtime) and reloads only changed folders; progress files are
written by atomic rename, which bumps the folder mtime, so transcription progress flows through
the same path. Search queries the FTS index; the index is synced in a background thread at
start and on query.

### Threads

`QThreadPool` with `QRunnable` jobs for: recovery at start, index sync, import batches,
waveform peaks, doctor, model download polling. Results return through Qt signals on a
`QObject` bridge. The recorder and worker are separate processes already.

### Recorder UI

A 100 ms timer reads the active session's status and the tail of the current take for the meter;
when idle, a `LevelMonitor` on the selected source feeds it. Starting a recording stops the idle
monitor first (one capture stream per source). The recording row in the list is the
recording's folder with `state: recording`.

### Player

`QMediaPlayer` + `QAudioOutput`. On a media error the file is converted once to FLAC in
`~/.cache/echo/playback/<sha>.flac` and reloaded. Crop is enforced in `positionChanged`.
Waveform peaks (min/max per 10 ms at 8 kHz decode) are cached in
`~/.cache/echo/peaks/<sha>.npy`. Snapping looks for the quietest 10 ms bucket within ±0.3 s.

### Editor

`QPlainTextEdit`. Autosave via a 1 s single-shot timer restarted on each change, plus explicit
saves on selection change and quit. Passage mapping (follow-along, Ctrl+click) is computed only
for unedited model text by rebuilding the same join as the worker and recording character spans.

### Lifecycle

- Single instance through `QLocalServer` named `echo-app-<uid>`; a second process sends
  `show` and file paths, then exits.
- Close during recording: hide to tray with a notification; tray menu offers Show, Stop
  recording, Quit (quitting leaves the recorder running).
- First run is detected by the absence of the settings file.

## Risks / Trade-offs

- [QtMultimedia FFmpeg backend lacks a codec (e.g. AMR)] → cached FLAC conversion.
- [Very large libraries] → scanning is O(folders) per second; fine to several thousand.

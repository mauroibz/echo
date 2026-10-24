# desktop-app Specification

## Purpose
The desktop window through which the user records, imports, finds and opens recordings, and the
lifecycle rules that keep it fast, predictable and safe for recordings in progress.

## Requirements

### Requirement: Fast start
The window SHALL be interactive within one second of launch on the reference machine, with
recovery, indexing and model checks running in the background.

#### Scenario: Launch with a large library
- **WHEN** Echo starts with hundreds of recordings
- **THEN** the window and the recorder controls are usable before the search index finishes updating

### Requirement: Single instance
Launching Echo while it is running SHALL bring the existing window to the front instead of
opening a second one. Files passed to the second launch (for example "Open with Echo" from a file
manager) SHALL be imported by the running instance.

#### Scenario: Open with Echo
- **WHEN** Echo is running and the user opens a voice note with Echo from the file manager
- **THEN** the existing window comes to the front and the voice note is imported

### Requirement: Library list
The library SHALL list recordings newest first with title, date, duration and a status that updates
live: recording (with elapsed time), finalizing, queued, transcribing (with percent and time left),
transcribed, edited, failed, needs attention, recovered. An empty library SHALL explain how to
record or import. A search box SHALL filter by title and transcript text, ignoring accents and case.

#### Scenario: Live transcription status
- **WHEN** a recording is being transcribed
- **THEN** its row shows the percentage and time remaining, updated at least every few seconds,
  and the row changes to transcribed when done without user action

#### Scenario: Search ignores accents
- **WHEN** the user types "reunion"
- **THEN** recordings whose title or transcript contains "reunión" are listed

### Requirement: Drag and drop import
Dropping files or folders anywhere on the window SHALL import them, showing progress and a summary
of imported, duplicate and rejected files. Dropped web links that are not local files SHALL be
rejected with a message.

#### Scenario: Drop a WhatsApp note
- **WHEN** the user drops a `.opus` voice note on the window
- **THEN** it appears in the library, selected, and transcription starts if enabled

### Requirement: Recording controls
The recorder area SHALL offer source selection, a live level meter with clip indication, a listen
toggle, record, pause and stop, the elapsed recorded time, and any recorder warning. While
recording, the window title and a tray icon SHALL show that recording is in progress.

#### Scenario: Record from the window
- **WHEN** the user presses Record, speaks, and presses Stop
- **THEN** the new recording appears at the top of the library, becomes playable when saved, and
  is queued for transcription if enabled

### Requirement: Closing never stops a recording
Closing the window while recording SHALL keep the recording running. The user SHALL be told that
recording continues and how to return to it. Reopening Echo SHALL show the recording in progress.

#### Scenario: Close during recording
- **WHEN** the user closes the window during a recording
- **THEN** the recording continues, a tray icon offers to show Echo or stop the recording, and no
  audio is lost

### Requirement: Silent recovery
On start, recordings interrupted by a crash SHALL be recovered without questions and marked as
recovered in the library.

#### Scenario: Start after power loss
- **WHEN** Echo starts after a power cut during a recording
- **THEN** the recording appears with its audio and a "recovered" mark

### Requirement: First run
On first launch Echo SHALL show a single welcome screen to choose the microphone with a live level
meter and, when transcription is installed but the models are missing, to download them with a
progress bar (or explain how to get access if not logged in to Hugging Face). Skipping it SHALL
leave a fully working recorder.

#### Scenario: Skip the download
- **WHEN** the user closes the welcome screen without downloading the models
- **THEN** recording works, and transcription actions explain how to download the models

### Requirement: Settings and setup check
Settings SHALL fit on one page: data folder, sample rate, mono or stereo, automatic transcription,
Spanish adapter, and worker idle time. A "Check setup" dialog SHALL show the doctor results with
fixes.

#### Scenario: Change sample rate
- **WHEN** the user sets the sample rate to 44.1 kHz
- **THEN** the next recording uses 44.1 kHz

### Requirement: Keyboard access
Every action SHALL be available from the menu with a visible shortcut where one exists, including
record or stop, pause, play or pause, rename, delete, find, copy transcript, import and export.

#### Scenario: Record by keyboard
- **WHEN** the user presses Ctrl+R
- **THEN** recording starts, and pressing Ctrl+R again stops it

### Requirement: Layout persists
Window size, pane sizes, the selected recording and playback speed SHALL be restored on the next launch.

#### Scenario: Reopen
- **WHEN** the user resizes the panes, quits and reopens Echo
- **THEN** the panes have the same sizes and the same recording is selected

### Requirement: Visual identity and appearance
Echo SHALL ship its own look, independent of the desktop theme: bundled icons and interface
typeface, a deep sidebar with the recorder and library, and the selected recording on light
cards. Light SHALL be the default appearance; the user SHALL be able to choose dark or to follow
the system, and the change SHALL apply without restarting. Recording SHALL be signalled in coral
in the recorder, the library row and the window title. Animation SHALL stop when there is
nothing to show (no input and no recording) and while the window is hidden.

#### Scenario: Switching appearance
- **WHEN** the user picks Dark in Settings
- **THEN** every open window repaints in the dark palette, including icons and custom-drawn parts
- **AND** cancelling the dialog restores the appearance that was showing before

#### Scenario: Same look on any desktop
- **WHEN** Echo runs on a machine without the Breeze icon theme or the Manrope font
- **THEN** it shows the same icons and typeface as on the developer's machine

#### Scenario: Waves follow the input
- **WHEN** the selected input picks up sound before or during a recording
- **THEN** the waves under the recorder rise with the level, and settle when the input is silent

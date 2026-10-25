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
The list SHALL show recordings newest first, grouped by month, with title, date, duration and
status, and SHALL filter by search text and by tags shown as chips above it. Selecting a
recording SHALL show its tags, notes and statistics (words, words per minute, silence share).

#### Scenario: Filter by tag
- **WHEN** the user clicks the "entrevista" chip
- **THEN** only recordings with that tag are listed, and the chip shows as active until cleared

### Requirement: Search everything, then find in one
Ctrl+Shift+F (and Ctrl+K) SHALL focus the search of all recordings, and Ctrl+F SHALL find within
the open transcript. Selecting a recording while a search is active SHALL open its transcript
with the search's words already found, without moving the keyboard focus out of the list. When
the words are not a phrase in that transcript, each word SHALL be found on its own.

#### Scenario: Open a search result
- **WHEN** the user searches all recordings for "precio" and clicks a result
- **THEN** its transcript shows with "precio" found and highlighted, and the arrow keys still move in the list

### Requirement: Drag and drop import
Dropping audio or video files, or folders, anywhere on the window SHALL import them, showing
progress (including progress within a file whose audio is being extracted) and a summary of
imported, duplicate and rejected files. The drop overlay SHALL read "Drop audio or video to
import" and the open dialog SHALL list audio and video files. Dropped web links that are not
local files SHALL be rejected with a message.

#### Scenario: Drop a WhatsApp note
- **WHEN** the user drops a `.opus` voice note on the window
- **THEN** it appears in the library, selected, and transcription starts if enabled

#### Scenario: Drop a meeting video
- **WHEN** the user drops an OBS screen recording on the window
- **THEN** it appears in the library as an audio recording, selected, and transcription starts if enabled

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
Window size, pane sizes, the selected recording and playback speed SHALL be restored on the next
launch. Each recording's and each linked set's volume SHALL be remembered and restored when it is
selected; one that was never changed plays at 100%.

#### Scenario: Reopen
- **WHEN** the user resizes the panes, quits and reopens Echo
- **THEN** the panes have the same sizes and the same recording is selected

#### Scenario: Volume follows the recording
- **WHEN** the user sets a quiet meeting to 300%, selects a voice note, then the meeting again
- **THEN** the voice note plays at 100% and the meeting at 300%, also after Echo is restarted

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

### Requirement: Sets in the list
A set SHALL appear as one row in the list, placed by its newest part, showing its title, the
number of parts, the total length and a status summarizing the parts, and SHALL expand to show
its parts as indented rows. A search or tag filter SHALL show a set when any of its parts
matches, with the matching parts shown.

#### Scenario: Expanding a set
- **WHEN** the user clicks the chevron of a set of three voice notes
- **THEN** the three parts appear beneath it in order, and selecting one shows that recording alone

### Requirement: Linking recordings
The user SHALL be able to link recordings by selecting several rows and pressing Link (or
Ctrl+L), and by dragging a row onto another row or onto a set; to reorder parts by dragging or
with Alt+Shift+Up and Alt+Shift+Down; and to unlink from the context menu or by dragging a part
out. Deleting a set row SHALL ask whether to unlink the set, which is the default, or move all
its parts to the trash.

#### Scenario: Link three selected recordings
- **WHEN** the user Ctrl+clicks three voice notes and presses Link
- **THEN** one set row replaces them, ordered by date, and it is selected with the three transcripts shown one under the other

#### Scenario: Deleting a set
- **WHEN** the user presses Delete on a set row and confirms with the default button
- **THEN** the set is unlinked and its parts are listed as separate recordings again

### Requirement: Offer to link a burst
After an import, voice notes that look like one burst SHALL be offered for linking in a
single-line banner above the list with a one-click Link action and a dismiss button. An offer
SHALL never link without the click, and a dismissed offer SHALL NOT be shown again.

#### Scenario: Three consecutive WhatsApp notes
- **WHEN** the user drops PTT-20261023-WA0004, WA0005 and WA0006 on the window
- **THEN** after the import a banner offers to link the three voice notes, and one click on it creates the set

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
The list SHALL show recordings newest first, grouped by Today, Yesterday, This week and then by
month. A row SHALL show the title and, under it, the time or day, the length and the number of
speakers when there are several; a status SHALL show only when it needs attention or reports
work (recording, saving, transcribing with its progress, waiting, failed, not transcribed,
passages to check). The list SHALL filter by search text and by tags chosen from chips that
open from a filter button in the search field. Selecting a recording SHALL make its tags
visible in its header and its notes and statistics (words, words per minute, silence share)
available in Details.

#### Scenario: Filter by tag
- **WHEN** the user opens the filter in the search field and clicks the "entrevista" chip
- **THEN** only recordings with that tag are listed, and the chips stay shown with "entrevista" active until it is cleared

#### Scenario: A finished recording is quiet
- **WHEN** a recording made today has been transcribed
- **THEN** its row under Today shows its title, the time, the length and the speakers, and no status

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
At rest the recorder area SHALL show the Record button and the name of the input, which opens a
panel with the input list, a live level meter with clip indication, a listen toggle, the input
gain and the computer-audio option. A silent input SHALL be named under the button. While
recording, the area SHALL show the state, the elapsed recorded time, the level, pause, stop,
add marker, and any recorder warning. While recording, the window title and a tray icon SHALL
show that recording is in progress.

#### Scenario: Record from the window
- **WHEN** the user presses Record, speaks, and presses Stop
- **THEN** the new recording appears at the top of the library, becomes playable when saved, and
  is queued for transcription if enabled

#### Scenario: Check the microphone before recording
- **WHEN** the user clicks the input's name under Record
- **THEN** a panel opens with the inputs and a level meter that moves with the microphone

### Requirement: Closing never stops a recording
Closing the window while recording SHALL keep the recording running and show the recording dock
(and, where there is one, the tray icon). Reopening Echo SHALL show the recording in progress.

#### Scenario: Close during recording
- **WHEN** the user closes the window during a recording
- **THEN** the recording continues, the dock shows its time with Pause, Stop and Marker, a tray
  icon offers to show Echo or stop the recording, and no audio is lost

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
Every action SHALL be available from the menu button at the top of the sidebar (also opened with
F10) with a visible shortcut where one exists, including record or stop, pause, play or pause,
rename, delete, find, copy transcript, import and export. Shortcuts SHALL work without opening
the menu.

#### Scenario: Record by keyboard
- **WHEN** the user presses Ctrl+R
- **THEN** recording starts, and pressing Ctrl+R again stops it

### Requirement: Layout persists
Window size, the sidebar's width, whether Details is open, the selected recording and playback
speed SHALL be restored on the next launch. Each recording's and each linked set's volume SHALL
be remembered and restored when it is selected; one that was never changed plays at 100%.

#### Scenario: Reopen
- **WHEN** the user widens the sidebar, opens Details, quits and reopens Echo
- **THEN** the sidebar has the same width, Details is open and the same recording is selected

#### Scenario: Volume follows the recording
- **WHEN** the user sets a quiet meeting to 300%, selects a voice note, then the meeting again
- **THEN** the voice note plays at 100% and the meeting at 300%, also after Echo is restarted

### Requirement: Visual identity and appearance
Echo SHALL ship its own look, independent of the desktop theme: bundled icons and interface
typeface, a deep sidebar with the recorder and library, and the selected recording on a light
card with no menu bar or status bar around it. Light SHALL be the default appearance; the user
SHALL be able to choose dark or to follow the system, and the change SHALL apply without
restarting. Speakers' colors and the transcript's text SHALL keep their contrast in both
appearances. Recording SHALL be signalled in coral in the recorder, the library row and the
window title. Animation SHALL stop when there is nothing to show (no input and no recording) and
while the window is hidden.

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

### Requirement: Tag categories in the window
The tag bar SHALL open from the filter button in the search field, and SHALL show by itself while
the search holds a tag. It SHALL show one chip per category, whose menu lists the category's
values with their counts and an entry for any value, beside the plain tags. Choosing an entry
SHALL add the tag to the search box, which stays the one place the filter lives. The tag editor
SHALL show a categorized tag with its category set apart, and typing `category:` SHALL complete
that category's values.

#### Scenario: Filter by a client from the bar
- **WHEN** recordings are tagged `client:Acme` and `client:Globex` and the user opens the filter, then the "client" chip, and picks Globex
- **THEN** the search box holds `#client:Globex` and only Globex's recordings are listed

### Requirement: Search by speaker
`@name` in the search SHALL limit the results to recordings where a speaker with that name
speaks, where the name is matched by its words from their start, without case or accents, and
`_` joins words of one name; several `@name` SHALL all have to speak. With words as well, the
words SHALL have to be in passages of the named speakers, each result SHALL show the matching
passage text with the speaker's name, and opening a result SHALL find the words only within
those speakers' passages, starting at the first match. Typing `@` SHALL offer the names of the
people who speak in the library. Only speakers the user named, or Echo named as the user, can
be found this way.

#### Scenario: What Ana said about the price
- **WHEN** Ana and Pedro both said "precio" in one meeting, only Pedro did in another, and the user searches `@ana precio`
- **THEN** only the first meeting is listed, with Ana's words under its title, and opening it highlights "precio" in Ana's passages only

#### Scenario: Which meetings was Ana in
- **WHEN** the user searches `@ana`
- **THEN** every recording where a speaker named Ana López speaks is listed

### Requirement: People and profiles
A People window SHALL list every person in the dictionary and everyone named as a speaker, with
the number of recordings they speak in, filtered by typing. A person's profile SHALL show and
save free notes, their aliases, their tags, and their recordings with how long they spoke in
each, newest first; opening one SHALL show that recording in the main window. Where their voice
is known, the profile SHALL play a few seconds of them and offer to forget the voice. The
profile SHALL also open from a speaker's name in the transcript.

#### Scenario: From a speaker to everything about them
- **WHEN** the user clicks "Ana" beside a passage and chooses "Open profile"
- **THEN** Ana's profile lists the three calls she speaks in with her speaking time in each, the user writes "CFO de Acme" in her notes and tags her `client:Acme`, and after restarting Echo both are still there

### Requirement: The selected recording
The selected recording SHALL show a header with its title, one line with its date, length and
speakers, its tags, and buttons to copy, export (transcript or audio), open Details and reach the
transcript's other actions; its transcript as a reading column; and a player along the bottom
with play, the time, the waveform with markers and crop, the length, the speed and the volume.
Details SHALL hold the notes, the markers (each plays from its time when clicked), the context
line, the file, the statistics and how the transcript was made.

#### Scenario: Notes are one click away
- **WHEN** the user selects a meeting with notes and presses Details
- **THEN** a panel at the right shows the notes, editable, with the meeting's markers, context line, file and statistics

### Requirement: Messages
Short messages (an import's summary, a saved recording, a failed action) SHALL show for a few
seconds over the bottom of the window and then go, without a status bar.

#### Scenario: Import summary
- **WHEN** the user drops three voice notes on the window
- **THEN** "Imported 3." shows over the bottom of the window and goes after a few seconds

### Requirement: Motion
Changes of state SHALL be shown with short motion (120 to 420 ms): the recorder entering and
leaving recording, a pulsing dot while recording and a slow amber blink while paused, a ring on
the marker button and a marker dropping onto the waveform, a new recording sliding into the
list, a sweep along a running transcription's progress, the play icon crossing to pause,
smooth scrolling to the passage that plays, Details sliding open and closed, and messages fading.
A "Reduce motion" setting, on by itself when the desktop has animations turned off, SHALL stop
all of it while the time, levels and progress still update. Nothing SHALL animate while the
window is hidden.

#### Scenario: Recording starts
- **WHEN** the user presses Record
- **THEN** the recorder's coral block fades in and the dot beside "RECORDING" pulses until Pause or Stop

#### Scenario: Reduce motion
- **WHEN** GNOME's animations are off and the user presses Record
- **THEN** the recorder shows the recording state at once and the dot stays still, and the time still counts

### Requirement: Recording dock
A small dock SHALL let the user record without the window: at rest, Record and the input; while
recording, the time, the level, what is recorded, Marker with a count, Pause, Stop and a way back
to the window; while paused, the time blinking in amber; after Stop, that the recording was
saved and its transcription progress, with Open and Done. It SHALL float above other windows
where the desktop allows it, be moved by dragging, remember its place, shrink to the time while
recording when the pointer is away, and show problems with the input. Ctrl+Shift+D SHALL swap the
window and the dock.

#### Scenario: Record a call from the dock
- **WHEN** the user presses Ctrl+Shift+D, then Record in the dock, marks twice and presses Stop
- **THEN** the window is hidden throughout, the dock shows the time and "2" beside Marker, and after Stop it says the recording was saved, and Open shows it selected in the window

### Requirement: Screens and passages for extensions
An extension SHALL be able to add a screen shown in place of the selected recording, opened and
closed by a button beside People and closed by choosing a recording in the list; to show a
recording playing from a time; to add sections under a person's notes in People; and to get the
passages matching a search with their recording, times, speaker and text. Without an extension
the window SHALL be unchanged.

#### Scenario: A citation
- **WHEN** an extension's screen calls `show_recording(id, at=12.5)`
- **THEN** the screen closes, the recording is selected and plays from 0:12

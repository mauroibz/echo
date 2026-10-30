## MODIFIED Requirements

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

## ADDED Requirements

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

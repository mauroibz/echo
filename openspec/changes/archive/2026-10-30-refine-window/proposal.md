# Proposal

## Why

The window does everything it should, but it shows everything at once: a menu bar, the input
picker, a level meter, the computer-audio toggle and an idle timer before anything is recorded,
a tag cloud over the list, "Transcribed" on every row, three lines of file details and
statistics, the context line and notes under the title, a volume slider with its percentage, and
a technical line over the text ("Model transcript · Spanish adapter"). Each piece was added for a
reason, and together they make the window feel crowded and unfinished. The look (Lagoon colors,
Manrope, the deep sidebar, the waves) stays; what changes is how much is on screen at a time.

## What Changes

- **No menu bar.** Its menus move unchanged into a menu button at the top of the sidebar (also
  F10), next to a People button. Every shortcut keeps working.
- **No status bar.** Messages appear for a few seconds as a toast over the bottom of the content.
- **Recorder at rest:** the wordmark, one Record button and the input's name under it. The input
  name opens a panel with the input list, listen, gain, computer audio and a level meter. The
  waves still rise with the input, and a silent input is still named under the button.
- **Recorder while recording:** a coral block with the state, the time, the level, and Pause,
  Stop and Marker buttons.
- **Search** reads "Search" with its shortcut, and the tag chips hide behind a filter button in it
  (shown by themselves while a tag filters the list).
- **The list** is always grouped by date (Today, Yesterday, This week, then months). A row shows
  the title and, under it, the time or day, the length and the number of speakers; the status
  appears only when there is something to say (recording, transcribing, waiting, failed, not
  transcribed).
- **The selected recording** shows a header with its title, one line (date, length, speakers)
  with its tags, and Copy, Export, Details and More buttons; the transcript as a reading column;
  and a player docked along the bottom (play, time, waveform with markers and crop, length,
  speed, volume in a pop-up).
- **Details,** a panel at the right that opens with its button and remembers whether it is open,
  holds what was always on screen before: notes, markers, the context line, the file, the
  statistics, and how the transcript was made.
- **Speakers' names** sit above their turns, with a colored dot, instead of in a column at the
  left of the text. Passage times stay in the margin, with their toggle.
- **Dark mode:** the transcript's text is a little softer than titles, and speakers get colors
  that keep their contrast on both themes.

Animation and a compact recording dock are separate changes (`add-motion`, `add-record-dock`).

## Capabilities

### Modified Capabilities
- `desktop-app`: library list, recording controls, keyboard access, layout persistence,
  visual identity, tag bar; added the selected recording's layout and messages.
- `transcript-editor`: the context line moves to Details; speaker names above turns.

## Impact

`ui/main_window.py` (menus in a button, toast, header, details, layout), `ui/recorder_panel.py`
(rest and recording states, input panel), `ui/player.py` (player dock, speed and volume
buttons, header and details parts), `ui/transcript.py` (toolbar moved to the header, speaker
names above turns), `ui/library_view.py` (date groups, rows), `ui/theme.py` (tokens and styles),
new `ui/details.py`; UI tests updated where widgets moved; `docs/guide.md`, `docs/design.md`,
`README.md` screenshot, `CHANGELOG.md`. No new dependency, no change to files on disk.

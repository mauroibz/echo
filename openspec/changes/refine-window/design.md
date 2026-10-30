# Design

The reference is the canvas the user approved on 2026-10-29: the current window, the proposal
selected in light and dark, recording with Details open, and the motion and dock boards (those
two belong to later changes).

## Decisions

- **Parts stay, places change.** The widgets keep their names on `RecorderPanel`, `PlayerPanel`
  and `TranscriptPanel` (`player.title`, `player.wave`, `transcript.status`, `recorder_panel.meter`
  and so on), so signals, extensions (`window_class`, `add_view`) and most tests keep working.
  `PlayerPanel` gains three containers that the window places: `header` (title, one line, tags),
  `dock` (playback) and the pieces of Details. `PlayerPanel` itself is no longer laid out.
- **Menus in a button.** `_build_menus` fills a `QMenu` with the same submenus instead of the
  menu bar, and the window keeps every action (`addAction`), so shortcuts work with the bar
  gone. The button sits in the sidebar's top row with People; F10 opens it, the usual key for
  an application menu. Help → Keyboard shortcuts stays the list of every shortcut.
- **Toast instead of the status bar.** `show_message` shows a rounded label over the bottom of
  the content for 4 s (longer text, 6 s); a new message replaces the old one. The worker line
  ("Transcribing · 2 in queue") is dropped: each row already shows its own transcription state.
- **Recorder.** One `recblock` frame holds the state line, the time and the meters (shown only
  while recording) and the button row: Record alone at rest; Pause, Stop and Marker while
  recording. Under it at rest, a flat button with the input's name opens `InputPanel`, a popup
  with the input list, listen, gain, computer audio and its own level meter fed by the same
  monitor. The silent-input note shows on that button in amber. The waves under the recorder
  are unchanged and keep following the input at rest.
- **Tags behind a filter.** A filter action at the end of the search field shows or hides the
  tag bar; the bar shows itself while the search holds a `#tag`, so an active filter is never
  hidden.
- **Date groups.** Rows are grouped always, by Today, Yesterday, This week (Monday on), then by
  month ("October", with the year when it is not this year). A row's second line is the time
  (today, yesterday), the weekday (this week) or the date, then the length ("33 min",
  "1 h 30 min", "41 s"), then "3 speakers" when the transcript has more than one. The number of
  speakers is computed with the status and cached with it, not on paint.
- **Statuses.** Done and Edited show nothing; ⚑ with a count stays, small, for passages to
  check. Recording, saving, transcribing (with its bar), waiting, failed and needs-attention keep
  their pills.
- **Header actions.** Copy (the transcript), Export (a menu: transcript…, audio…), Details (a
  toggle) and More (the transcript's existing menu with Times added). The transcript's own
  toolbar is hidden; `transcript.status` moves to Details.
- **Details.** `DetailsPanel` (new `ui/details.py`) is a scrollable card at the right of the
  transcript: Notes (`player.notes`), Markers (a list built from the recording's markers; a click
  plays from it), Context for transcription (`player.context`), File (source, recovered,
  interruptions, crop with Clear), Statistics (`player.statistics`) and Transcript
  (`transcript.status`). Open or closed is kept in the UI state. While a set is shown, the pieces
  that belong to one recording hide as they do today.
- **Player dock.** Play, current time, the waveform (44 px tall, same widget, same crop and
  marker editing), total time, a speed button that cycles through 1×, 1.25×, 1.5×, 2× (and offers
  them in a menu), and a volume button that opens a popup with the slider and the reset
  percentage. The combo box and slider attributes stay (`player.speed`, `player.volume`,
  `player.volume_label`), inside the button and the popup.
- **Speaker names above turns.** A turn that follows a blank line gets its name drawn in that
  blank line, at the text's left edge, with a dot in the speaker's color; clicking it opens the
  same menu as the margin label did. The first turn gets the space from the document's top
  margin. A turn that does not follow a blank line (the user joined paragraphs) keeps its name
  in the margin, so no name ever covers text.
- **Tokens.** `orange` and `violet` are added for speakers, readable on the surface in both
  themes; `prose` is the transcript's text color (equal to `ink` in light, softer in dark).
  Speaker colors become accent_deep, orange, violet, coral_deep, muted.

## Decisions made while implementing

- "Not transcribed" shows on a row only when transcription is installed; without it every row
  would say so. Whether it is installed is looked up once per run, since rows ask on every
  refresh.
- `QPlainTextEdit` ignores per-block line heights and top margins (checked: the block heights did
  not change), so a speaker's name sits in the blank line before the turn, in a slightly smaller
  bold face, and the document margin grows from 14 to 34 px only when the first paragraph has a
  name over it.
- The volume button shows the percentage beside its icon when it is not 100%, so a boosted
  recording says so without opening the popup.
- `editor.labels` keeps every speaker name, wherever it is drawn; `margin.labels` holds only the
  ones in the margin. Tests that read names use the former.
- The list model gains `shown()`, the rows that are recordings or sets, since headings are now
  always there; tests that counted rows use it.

## Risks

- Moving widgets breaks tests that look at visibility (`isVisible` on a widget now inside a
  closed popup). Those tests change to `isVisibleTo` the popup; behavior tests stay as they are.
- A hidden menu bar must not hide actions from screen readers: the menu button has an accessible
  name and every action keeps its text and shortcut.

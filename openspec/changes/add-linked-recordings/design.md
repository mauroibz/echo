# Design

## Context

A recording is a folder with `meta.json`, its audio and its transcripts, and the SQLite index
is a cache rebuilt from the folders. The list (`ui/library_view.py`) is a flat model of
recording ids, newest first, with month headings. The transcript panel and the player each
hold exactly one `Recording`. Imports derive a title and date from the file name, and
WhatsApp's names carry either a full time (desktop exports) or a date and a running number
(`PTT-20261023-WA0003`, Android).

## Goals and non-goals

Goals: link recordings into an ordered set in one gesture; read, edit, search, play and export
the set as one; never change a member's audio or its own files by linking. Non-goals: merged
audio, nested sets, one recording in two sets, a transcription job per set.

## Decisions

### Storage: one small file per set

`<data>/sets/<set id>.json`, written atomically through `fsutil`:

```json
{"id": "set_2026-10-24T13-40-00_ab12", "title": "Audios de Lucía",
 "title_auto": true, "members": ["2026-10-23T14-02-11_9f3e", "2026-10-23T14-04-30_77a1"],
 "created": "2026-10-24T13:40:00-03:00"}
```

- The member order is the list order; nothing else holds membership, so there is one place to
  read and nothing to keep consistent. Members' folders are untouched, which keeps "copy a
  folder to move a recording" true and avoids rewriting several `meta.json` files (and several
  sync conflicts) to reorder.
- Members that are missing (in the trash, or not synced yet) are skipped, not removed. A
  restored recording therefore comes back into its set. A set with fewer than two present
  members shows as its remaining recording. Deleting a recording does not write the set file.
- One recording is in at most one set. Linking a member of set A into set B moves it (A's file
  is rewritten without it, B's with it). If two files claim the same recording (a sync
  conflict), the most recently modified file wins when loading, and the other's claim is
  ignored until it is next written, which drops it.
- A set whose file lists no present members is removed by `rescan`; "Unlink" deletes the file.
- The index gets a `sets` table (id, title, members as JSON, newest member's `created`) for
  the list and the CLI, rebuilt like everything else (schema 3).

### Title

A new set's title is the first part's title with the count ("WhatsApp voice note 2026-10-23
14:02 (+2)"), and `title_auto` is true. When the first part's transcript is ready and the set
has not been renamed, the title becomes its first sentence, as auto titles of recordings do.
Renaming (F2 on the set row, or the title field when the set is shown) sets `title_auto` false.

### The list

- A set is one row in the list's ordering, placed by its newest part's `created`. The row looks
  like a recording row with a stacked-cards glyph, "3 parts" and the total cropped length. Its
  status pill summarizes the parts: transcribing (with the number left), failed if any failed.
- A chevron at the row's right expands the parts as indented, shorter rows (title, length,
  status). Expanded state is per set, kept in `UiState`. Keyboard: Right expands, Left
  collapses or moves to the parent row, as in a tree.
- Selecting the set row shows the set; selecting a part row shows that recording alone, exactly
  as today.
- The model stays a flat `QAbstractListModel` with three kinds of rows (heading, set, part) and
  the existing delegate gains the two new shapes; a `QTreeView` would mean restyling the whole
  list for one level of nesting.
- Search and tags: the index search returns recording ids; a set row is shown when any member
  matches, and when it is collapsed the matching parts are expanded automatically while the
  search is active. Carrying the search into the transcript (Ctrl+Shift+F) works on the set view
  unchanged.

### Linking with the fewest clicks

- **Multi-selection.** The list moves to extended selection. When two or more rows are selected,
  a bar slides up at the bottom of the list: "3 selected · Link · Delete…". Link (or Ctrl+L)
  creates the set in date order (or appends to the set if one selected row is a set) and
  selects it, so the result is on screen immediately. Single selection behaves as today; the
  current item still drives the panels.
- **Drag and drop.** Dragging a recording row onto the middle of another row links them; onto a
  set row adds it at the end; between two part rows inserts it there, which is also how parts
  are reordered. Dropping a part between top-level rows takes it out of its set. The drop target
  is drawn as a highlight (link) or an insertion line (place), so the result is visible before
  release. File drops on the window keep importing as now.
- **Keyboard reorder.** Alt+Shift+Up and Alt+Shift+Down move the selected part within its set
  (Alt+Left and Alt+Right already move between markers).
- **Burst offer after import.** See below. One click on the banner links.
- **Context menu.** "Link with…" is not added: selection plus Link covers it. The menu gains
  "Remove from set" on a part and "Unlink" on a set.

### Burst detection

`sets.bursts(recordings)` groups recordings, taken from one import (a drop, File → Import, a
CLI import) plus the library's recordings from the same day, into runs where each next
recording:

- is a WhatsApp voice note or audio like the previous one, and
- has a desktop-export time within 10 minutes after the previous one's end (start plus
  duration), or, with Android names, the same date and the next `WA` number (gaps of up to 2
  allowed for skipped photos and files in the same chat export).

Runs of two or more, none of whose members is already in a set, become offers. The window shows
one banner above the list, "3 voice notes from 23 Oct look like one conversation · Link them ·
×", and selecting it highlights those rows. Dismissing with × remembers the offer's members
(in `UiState`) so it is not shown again. With several offers the banner shows the first and
says "1 of 2". Recordings made with Echo's recorder are not offered: a stop is a deliberate end.

Watched folders import one file at a time; the same check runs against the library's last day,
so a note that follows a set already linked offers "Add to Audios de Lucía". The offer is never
applied without the click: guessing wrong would hide a recording inside a set.

### The set's transcript

The transcript panel shows a set with the same editor, built from a **part map**: an ordered
list of `(recording, start offset in the document, start time on the set timeline)`.

- Each part begins with a heading block (title, date and time, length; clicking the title
  selects that part alone). Heading blocks are not editable: the editor's key filter refuses
  edits that start in or cross a heading, so typing can never move text between parts.
- Editing: the autosave splits the document at the headings and saves each changed part through
  `save_edited`, as today, so the per-recording edit, revert and dictionary behavior is
  unchanged. The dictionary chip and corrections underlines work through the part map.
- Find, follow-along, low-confidence shading, passage times (Ctrl+T), Ctrl+. and the passage
  steps use the part map to turn positions into (part, position) and times into set time.
- Parts without a transcript show a one-line state under their heading ("Transcribing, 40%",
  "Not transcribed · Transcribe"); the rest of the set stays readable.
- The header area shows the set title and "3 parts · 6:12 · 23 Oct 14:02 to 14:09". The context
  line shown for a set ("who is speaking, what about") writes to every part, since a burst has
  the same people; tags and notes stay per part and are edited by selecting the part.

### Playback

The player gets a timeline of parts: each part's cropped span, laid end to end. Playing starts
the part that holds the playhead from the right offset; at its end the next part starts (one
ffmpeg decode per part, as now; the hand-over adds a few tens of milliseconds, which is not
audible between voice notes). The waveform shows the concatenated peaks (each part's cached
peaks, so no new decoding) with a thin divider and the part number at each boundary. Markers of
each part are shown at their set time; adding markers and cropping are done on the part, so the
crop handles are hidden in the set view.

### Export and command line

- Copy and Export on a set: plain text and Markdown with a heading per part; SRT, VTT and JSON
  with times on the set timeline. Export audio is not offered for a set (no merging).
- The vault export writes one note per set (each part a section, the parts' audio linked in
  order) and no separate notes for its parts.
- `echo-app link ID ID… [--title T]` creates or extends a set and prints its id;
  `echo-app unlink ID` (a set id dissolves it, a recording id removes it from its set);
  `echo-app list` prints sets with their parts indented; `echo-app export SET_ID` exports the
  set.

## Risks and trade-offs

- **Editing across parts in one editor** is the riskiest piece: a wrong split would save text
  to the wrong recording. Mitigations: headings are immutable blocks, the save compares each
  part's new text with what it loaded and writes only changed parts, and tests cover typing,
  pasting and deleting at every boundary. If the guard turns out to be fragile, the fallback is
  a read-only set view where a double-click opens the part at the same position.
- **Burst rules** are heuristics on file names. Wrong guesses cost one dismiss click; they never
  link anything on their own.
- **Set files and sync tools**: a set changed on two computers at once keeps the newer file.
  Members are never lost by this; only the set's order or title may revert.

## Open questions

None that block implementation; the thresholds (10 minutes, WA number gaps of 2) are set from
WhatsApp exports on the test data and recorded in `sets.py` with the files they were checked on.

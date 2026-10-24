# Proposal

## Why

Speech often arrives in pieces that belong together. WhatsApp caps a voice note's length, so a
six-minute explanation comes as three two-minute notes; a recording paused by stopping and
starting again becomes two. In the library these are separate rows, each with a fragment of the
thought, and reading the whole means clicking through them one at a time.

The audio files should stay as they are: merging would rewrite originals, lose each file's own
crop and transcript, and break the rule that an imported file is kept byte for byte. What is
missing is a way to say "these belong together, in this order" and to read and hear them as one.

## What Changes

- **Linked sets.** Two or more recordings can be linked into an ordered set. Nothing about the
  members changes: each keeps its audio, transcript, edits, tags and crop. A set is a small
  file in the data folder naming its members in order, with a title.
- **One row in the list.** A set shows as one row (title, total length, "3 parts"), placed by
  its newest part, with a chevron that shows the parts beneath it. Search and tag filters show a
  set when any part matches.
- **Read it as one.** Selecting a set shows the parts' transcripts one under the other, each
  under a thin heading with its title, time and length. The text is edited in place, and each
  part's edits are saved to that part. Find, copy and export work on the whole set.
- **Hear it as one.** The player plays the parts back to back on one timeline, with the part
  boundaries drawn on the waveform; Ctrl+click in the text and follow-along work across parts.
- **Few clicks to link.**
  - Select several rows (Ctrl or Shift click) and press Link in the bar that appears, or Ctrl+L.
  - Drag a row onto another to link them, or onto a set to add it.
  - After an import, voice notes that look like one burst (same chat export, consecutive
    numbers or minutes apart) are offered as a set: a one-line banner above the list with
    "Link them". Watched folders get the same offer for a new note that follows a recent one.
- **Unlinking** is in the context menu and by dragging a part out. Deleting a set row asks
  whether to unlink it (the default) or move all its parts to the trash.
- **Command line:** `echo-app link ID ID…`, `echo-app unlink ID`, and set ids accepted by
  `export`, `list` showing sets.

Out of scope: merging audio into one file, nesting sets, a recording in two sets, and
transcribing a set as one job (each part is transcribed on its own, as now).

## Capabilities

### Modified Capabilities
- `library-storage`: set files and their rules.
- `desktop-app`: set rows in the list, linking and unlinking, the burst banner.
- `transcript-editor`: the stacked transcript of a set, edited in place.
- `playback-and-crop`: continuous playback across parts.
- `audio-import`: detecting bursts of voice notes.

## Impact

New `sets.py` (set files, membership, burst detection); `library.py` (sets folder, delete
leaves sets intact); `index.py` (a `sets` table rebuilt from the files, schema 3);
`ui/library_view.py` (set rows, expansion, multi-selection, drag and drop); `ui/main_window.py`
(link bar, banner, Ctrl+L, context menu, delete prompt); `ui/transcript.py` (a part map so one
editor holds several recordings); `ui/player.py` (a timeline of parts); `export.py` (set
export, vault note per set); `cli.py`; `importer.py` and `ui/watch.py` (offer after import).
No new dependencies.

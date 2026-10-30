# Design

## Decisions

- **Screens instead of a subclassed window.** The roadmap's Studio window (S8) was to subclass
  `MainWindow` and add a sidebar. A stack in place of the recording, with a button per screen in
  the corner row, needs no subclass, keeps the sidebar and list as they are, and is a few lines
  in Echo. Choosing a recording in the list returns to it, so a screen never hides the list's
  meaning.
- **Passages from cues, not a new index table.** `passages` takes `list`'s matching recordings
  and scans their cues (the timed text the user sees). An index of passages would mean a schema
  change and a rebuild for a feature only an extension uses; the scan costs a few milliseconds
  per recording and stops at `limit`.
- **No Escape to leave a screen:** Escape already clears the search and closes find bars; one
  more meaning would make it ambiguous.

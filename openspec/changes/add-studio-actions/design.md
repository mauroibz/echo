# Design

## Decisions

- **Times from the transcript.** The request gets the summary and, up to 60,000 characters, the
  transcript with `[m:ss]` stamps, and answers each item's time as a stamp. Longer transcripts
  send the summary alone and the items have no time. Asking for a quote and searching for it
  was the alternative; a stamp is shorter and the model reads it off the same text.
- **Tolerant JSON.** The answer is the first `[...]` in the reply, so a code fence or a sentence
  around it does no harm; a bad date or time is dropped, not the item.
- **Owners are names as Echo knows them:** the request lists the recording's speaker names and
  asks for one of them when it fits. Filtering by person compares names folded, as tags do.
- **The Pending screen reads files.** Each refresh reads `actions.json` of every recording
  (the tag filter narrows them through the index first). For libraries of hundreds of
  recordings this is a few milliseconds per hundred; an index table would duplicate a file
  Studio owns.
- **S8 became a base hook.** The roadmap's Studio window (a subclassed `MainWindow` with its own
  sidebar) is replaced by `add_screen` in Echo: a stack in place of the recording, opened from
  the corner row. Pending is the first screen.

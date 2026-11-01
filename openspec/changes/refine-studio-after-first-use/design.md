## Decisions

- **Description is the model's; context and note are the user's.** The description comes with
  the item from the same extraction request, so it costs no extra request. Editing it marks the
  item edited, like its title. Context goes to the tracker with the item. The note is for the user
  only: the text output leaves it out, and the JSON names it so an agent can keep it out.
- **The star is Studio's, tags are Echo's.** Tags already exist on every recording and work in
  search, so the person page edits them through Echo's tag editor. A recording-level star has no
  place in Echo's `meta.json` without changing Echo, so it lives in `marks.json` beside Studio's
  other files.
- **Switches store only what differs from the default.** `skipped` holds meetings with a link
  switched off, and `wanted` holds meetings without one (or with the setting off) switched on. If
  the setting changes later, the meetings the user did not touch follow it. Entries are kept until
  a few days after the meeting ends.
- **Items beside the summary.** A splitter gives them a column as tall as the card, scrolling on
  its own. That also ends the empty strip, which came from the old list being sized to its
  content: rows added to a visible widget are shown only on the next event-loop pass, so measuring
  right after "Summarize again" counted none of them.
- **Ask withdrawn, not hidden.** The code is removed, since a disabled feature contradicts the
  repository's "no flags hiding unfinished work" rule; git history keeps it for when a concrete
  use case brings it back.

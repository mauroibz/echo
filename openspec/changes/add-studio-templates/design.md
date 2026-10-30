# Design

## Decisions

- **The tag is the choice.** Picking a template in the view or with `--template` writes the
  `template:` tag, so the automatic summaries, staleness and search all see the same choice, and
  the user can set it from the tag field before the transcript is ready. Only the first
  `template:` tag counts.
- **Built-ins in code, not files.** The app runs from a source tree without packaging data
  files; four short strings are simpler than a data folder.
- **Names match as tags do,** folded for case and accents. An unknown name falls back to the
  general prompt rather than failing an automatic summary; the CLI refuses it, since a typo there
  is a mistake the user can fix at once.
- **Hash.** The template's name and the hash of its text join the source hash only when a
  template is used, so summaries made without one stay current.

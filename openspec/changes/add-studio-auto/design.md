# Design

## Decisions

- **A second request over the summary,** not a title line asked of the summary prompt: that
  prompt is the one task 1.8 measures, and the summary is short, so the extra request costs
  little.
- **The title stays automatic** (`title_auto` remains true). A new transcript then gives it the
  first sentence again, and its new summary a new title; a rename by the user ends both. The
  recording is read again just before writing, so a rename made while the request ran wins.
- **A failed title is quiet:** the summary is saved and the first sentence stays; the CLI says so.

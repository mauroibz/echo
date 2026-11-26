# Design

- **In the core, parts from a hook.** The core cannot import Studio, and a bundle of transcripts
  alone is useful without it. `bundle_parts(rec)` returns `(key, label, heading, markdown)`: the
  key is what is remembered and what `--parts` names, the label is the dialog's, the heading is in
  the recording's language as the summary's already is.
- **The transcript goes last.** It is the longest part; the summary and the items read first.
- **One dialog, Copy as the default.** Choosing parts and choosing clipboard or zip are one step;
  with the ticks remembered (as the keys switched off, so a part that appears later starts on),
  a repeat bundle is the shortcut and Enter.
- **Laid out off the GUI thread.** Aligning edited text to passages takes a moment per long
  recording; the dialog only asks which parts exist, which reads no passages.
- **The zip is built in memory and written atomically**, with fixed entry times, so the same
  bundle is the same bytes. Text only, so memory is not a concern.

## Decisions made while implementing

- Several selected recordings are bundled oldest first; a single linked set keeps its parts' order.
- The user's private note on an action item stays out, as it does from the tracker.
- The message after a bundle gives a word count rather than the dialog, which would have to lay
  every transcript out before it could open.

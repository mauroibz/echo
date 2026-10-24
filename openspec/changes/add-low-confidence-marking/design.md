# Design

## Decisions

- **Signals.** Per passage: `short` (still under `min_words` after retries), `retried` (the
  kept text came from a fallback), and `logprob` (mean per-token log-probability from
  `generate(output_scores=True, return_dict_in_generate=True)`; implement only if it adds
  under 5% to GPU time on the 20-minute test recording, else leave it out and say so here).
- **Threshold.** A passage is `low` when its `logprob` is more than 1.5 standard deviations
  below the recording's mean (computed in the worker at the end of the job). Fixed
  thresholds do not transfer between microphones; the relative rule does.
- **Format.** `transcript.json` `version: 2`; each segment gains `flags: ["short", "retried",
  "low"]` (possibly empty) and `logprob` when available. Readers treat a missing `flags` as
  empty, so version 1 files keep working. The partial-results file carries the per-passage
  flags alongside texts.
- **Editor.** Flagged passages get a translucent warning-tinted background through the same
  extra-selections mechanism as follow-along; tooltip on hover gives the reasons in words
  ("very few words for 12 s of speech"). The status line shows "N passages to check"; it
  counts only passages whose current text still equals the model text (through the alignment
  from `add-timestamps-export`), so editing a passage clears its mark without extra state.
- **Navigation.** `Ctrl+Shift+.` from `add-edit-with-audio` jumps to the next flagged
  passage; the library list shows a small count badge when a transcript has flags.

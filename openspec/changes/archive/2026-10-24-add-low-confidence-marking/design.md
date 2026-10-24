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

## Decisions made while implementing

- **Cost of log-probabilities (1.1)**: on the RTX 3080, 20.7 minutes of audio took 6.82 s of
  recognition without scores and 6.91 s with them (median of three runs after a warm-up): +1.3%,
  under the 5% limit, with identical text. So `logprob` is included.
- **The engine API** keeps `transcribe()` (texts) and adds `transcribe_flagged()` returning
  `(text, flags, logprob)`; the worker uses the second when the engine has it, so stub engines
  and partial files from before keep working (old partials hold plain strings).
- **Retry on very low confidence.** Found while verifying: with a dictionary sentence in the
  context, one 8-second passage came back as "Debido a que no se puede" (logprob -1.17, the
  recording's mean -0.07), enough words to pass the short-output check. Passages below -0.5
  now get the same retries (style sentence only, then no context) and keep the more confident
  text; they are flagged `retried`. Measured range of ordinary passages: -0.01 to -0.17 on an
  audiobook and on the user's desk-microphone recording.
- **Relative rule** needs at least five passages with a log-probability.
- **The list** shows "Transcribed · ⚑ N" for unedited transcripts with flagged passages; the
  editor's status line shows "⚑ N passages to check" counting only passages still as the model
  wrote them.
- **Navigation** (`Ctrl+Shift+.`) is wired by add-edit-with-audio, using `next_flagged()` here.
- **Verified** on three audiobook chapters with the real model: 5, 1 and 1 passages flagged out
  of 63, 47 and 62; the flagged ones are the merged words, unpunctuated runs and the one
  passage that stayed a fragment after every retry.

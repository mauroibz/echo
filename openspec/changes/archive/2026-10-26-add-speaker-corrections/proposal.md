# Proposal

## Why

Speaker labels are per passage and come from voice clustering, so two mistakes cannot be fixed
today: a paragraph given to the wrong person, and someone cutting in inside a passage (a short
"¿cuánto?" from the other side), which the labels never see. Fixing them by hand makes
transcripts right, and every fix is a labeled example for tuning the speaker model later.

## What Changes

- **Said by.** Right-click in the transcript: "Said by ▸" lists the recording's speakers and
  "Someone else…". With no selection it changes the speaker of the paragraph under the pointer;
  with a selection, the selected words become that speaker's: whole passages are relabeled, and
  part of a passage is split off into its own paragraph with its own label.
- **Back to the speaker Echo found** undoes a fix at the pointer. **Join with the paragraph
  above** removes the break before a paragraph (a text edit, as typing it).
- Everything follows: margin labels, exports and subtitles (split text gets times estimated from
  its place in the passage), search by speaker, people's speaking times, the naming bar.
- Fixes are kept in `meta.json` with the passage, the speaker and their name at the time, the
  words for a split and their estimated times, and the transcript they were made on. A new
  transcription does not apply old fixes but keeps them: they are data for tuning later.

Splitting a passage inserts paragraph breaks, so the transcript becomes edited text, as typing
would. Fixes need speaker labels on the recording.

## Capabilities

### Modified Capabilities
- `transcript-editor`: correcting speakers in the text.

## Impact

`library.py` (`speaker_fixes`), `align.py` (cutting the text into speaker pieces, times),
`export.py`, `ui/transcript.py` (the context menu, labels, find, naming bar), `ui/people.py`,
`README.md`, `docs/design.md`, `CHANGELOG.md`. No new dependencies.

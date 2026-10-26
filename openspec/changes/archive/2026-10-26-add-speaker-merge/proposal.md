# Proposal

## Why

Speaker labeling sometimes splits one person into two speakers (a change of microphone distance,
a cough, a long pause). Giving both the same name hides most of it, but the margin repeats the
name at every switch, unnamed speakers cannot be joined without inventing a name, and the
recording keeps saying it has one more speaker than it has.

## What Changes

- **"Same person as…"** on a speaker's label menu lists the recording's other speakers; choosing
  one folds this speaker into it for that recording. The merged speaker keeps the other's number
  and name (or takes this one's name if the other had none).
- Everything follows the merge: one label in the margin, the naming bar asks once, the speaker
  count, exports, search by speaker, profiles and speaking times treat them as one. Naming a
  merged speaker teaches Echo the voice of both parts.
- **"Separate again"** on the merged speaker's menu undoes it.
- The merge is stored in `meta.json`; the model's `transcript.json` is untouched. Transcribing
  again finds the speakers afresh and drops the merges.

Out of scope: joining paragraphs that the speaker change started (the displayed text and its
paragraphs come from the transcript file, which a merge does not rewrite), merging across
recordings (that is naming them the same person).

## Capabilities

### Modified Capabilities
- `transcript-editor`: merging and separating speakers.

## Impact

`library.py` (`speaker_merges`, resolving and merging), `export.py`, `index.py`,
`worker/service.py` (dropping merges on a new transcript), `ui/transcript.py`, `ui/people.py`,
`README.md`, `docs/design.md`, `CHANGELOG.md`. No new dependencies.

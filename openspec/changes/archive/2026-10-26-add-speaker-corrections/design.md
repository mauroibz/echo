# Design

## Decisions

### Fixes as a list tied to their transcript

`meta.json` gets `speaker_fixes`, a list of `{transcript, segment, speaker, name}` plus `text`,
`start` and `end` for a split. `transcript` is the transcript's `created` time: segment indexes
belong to one transcription, so only fixes made on the current one apply. Fixes for an older
transcript stay in the list: each is a passage with its time span and the right speaker, which is
what tuning the speaker labeling needs.

### One function cuts the text into speaker pieces

`align.speaker_pieces(segments, text, spans, fixes)` turns the aligned passages into `(start,
end, segment, speaker)` pieces of the shown text: a whole-passage fix replaces the passage's
speaker, a split's words are found in the passage's span and cut out. Exports (`align.cues`), the
index (through the exports), the editor's margin and its find all use it, and then resolve merges
with `Recording.speaker`. A split is found by its exact words inside its passage; if the user
rewrites those words, the split no longer applies and the text is the passage's speaker's again,
rather than a guess about where it moved.

### Times for split text

The model times passages, not words. A piece's time is its passage's span scaled by the piece's
character position within the passage's text: good to a second or two in a passage of ordinary
speech, enough for subtitles and playing from a click.

### Splitting edits the text

The split words become their own paragraph by inserting paragraph breaks around them in the
editor, as an undoable edit, so the shown text, the labels beside it and every export agree. A
fix to whole passages changes no text.

### Who "Someone else" is

A new speaker number after every number in the recording; the user names them at once, as in the
margin. Fixes need the recording's speaker labels: a recording labeled as one voice has none.

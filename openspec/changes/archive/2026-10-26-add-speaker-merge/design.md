# Design

## Decisions

### A map in meta.json, resolved at one point

`meta.json` gets `speaker_merges` (speaker number to the number it was merged into), and
`Recording.speaker(n)` resolves a passage's number through it. Every reader of a passage's
speaker goes through it: export's `speaker_name` (so every export format and the CLI), the
index's speech per speaker, the transcript's labels, find and naming bar, and the People
window's voice sample. `transcript.json` stays the model's output, so a merge is undone by
removing an entry. Merging into a speaker that was itself merged resolves to the end of the
chain, and merging a speaker others were merged into moves them along, so the map stays flat.

### Names follow the kept speaker

The kept speaker's name wins; if it had none, the folded speaker's name moves to it. Separating
leaves the separated speakers unnamed: they were not that person, or the user would not separate
them.

### Voices

Naming a merged speaker folds the average of its parts' centroids into the person's voice, once
for the recording, so the parts count as one recording, as they are.

### Paragraphs stay

The worker starts a paragraph where the speaker changes, in `transcript.json`'s text. Undoing
those on a merge would rewrite the shown text and move every position the editor, its alignment
and an edited copy rely on. A merge relabels; the paragraph breaks stay.

### A new transcript drops the merges

Speaker numbers are the clustering's, and a new transcription numbers them afresh, so the worker
clears `speaker_merges` when it writes new speaker labels.

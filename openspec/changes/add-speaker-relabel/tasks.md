# Tasks

- [x] 1.1 Measure reassignment on the synthetic conversations of add-speaker-turns with simulated fixes; record the numbers in design.md
- [x] 1.2 The worker writes `transcript.voices.json` (voiceprints, interruptions, the transcript they belong to) and drops a stale relabeling; tests
- [x] 1.3 `relabel.reassign`, `relabel.relabel` and `restore`; `Recording.transcript()` reads the relabeling over the model's; tests
- [x] 1.4 The editor reassigns after Said by and after undoing a fix, says how many moved, and offers "Back to the speakers Echo found"; tests
- [x] 1.5 Voices kept as one part per recording; naming, renaming, merging and separating update this recording's part; the worker's own naming of the user too; tests
- [x] 1.6 README, `docs/design.md`, CHANGELOG
- [ ] 1.7 Check on a real meeting (needs a person: a real recording, transcribed again, fixed and listened to)

## Blocked

- **1.7** needs a person and a real recording. Transcribe again a meeting where two people were
  labeled as one speaker (or one person as two), fix three or four of the wrong paragraphs with
  "Said by", and listen to the passages the status bar says moved: most should now be right, and
  passages that were right before should stay right. If good passages move, raise
  `relabel.MARGIN`; if too few follow the fixes, lower it.

# Tasks

- [x] 1.1 Measure on synthetic Spanish conversations with interruptions (MLS Spanish readers, tune and held-out speakers, clean and room channel): today's labeling, segmentation cuts, embedding models, thresholds; record the numbers in design.md
- [x] 1.2 Pin the segmentation model in `models.py` as optional; doctor, the download dialog and `models status` count it
- [x] 1.3 `speakers.Segmenter`, local activity over 10 s windows, `speakers.cuts`; `planning.cut` splits passages at them; tests
- [x] 1.4 The worker finds the cuts before recognition and keeps them in the partial file; interruptions too short to embed take the nearest other speaker; threshold 0.35; tests
- [x] 1.5 README, `docs/design.md`, CHANGELOG
- [ ] 1.6 Check on real meetings with interruptions (needs hardware: real recordings, listened to)

## Blocked

- **1.6** needs real recordings. The numbers come from synthetic conversations (read speech,
  interruptions cut from other readers' sentences). A person should transcribe again two or three
  real meetings recorded on one microphone where someone interrupts long paragraphs with a few
  words, and listen at each speaker change in the editor: interruptions of a second or more
  should be paragraphs of their own with the other person's name, and there should be no more
  than a few wrong cuts per 10 minutes. If too many short ones are missed, lower
  `speakers.SEG_ACTIVE` (0.3 found more on the tuning set, with more false changes); if there are
  wrong cuts, raise `speakers.MIN_TURN`. "Said by" fixes made on these recordings are kept as
  labeled examples for that tuning.

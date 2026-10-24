# Tasks

## 1. Store and context

- [x] 1.1 `dictionary.py`: TOML load/save, entries, add/remove/merge/mute/touch; `context_sentence(extra, budget)`; unit tests including ordering and budget cut
- [x] 1.2 `transcription.request` builds and stores the context; `echo-app transcribe --context`; `meta.json` gains `context_line`; tests on the request file
- [x] 1.3 Add a case to `tests/test_model_smoke.py`: a dictionary sentence with ten names does not reduce the word count of the reference clip (needs hardware: GPU and the downloaded model)

## 2. Learning

- [x] 2.1 Candidate detection from a (model, edited) text pair with the capitalization, seen-twice, muted and common-word rules; bundle the frequency list with its license; unit tests
- [x] 2.2 Title candidates on rename
- [x] 2.3 The chip in `TranscriptPanel`: show after save, accept, decline; UI tests with the offscreen platform

## 3. Corrector

- [x] 3.1 `dictionary.correct()` with alias and fuzzy multi-token matching, folded comparison; `transcript.corrected.json` writer and per-recording rejected list; unit tests
- [x] 3.2 Editor shows corrected text with underlines, context-menu undo, re-run on dictionary change; `Recording.text()` precedence edited → corrected → model

## 4. Settings and docs

- [x] 4.1 Settings → Dictionary page: list, remove, merge, import
- [x] 4.2 README section "Names and terms"; `docs/design.md` Next section updated
- [x] 4.3 Verify end to end on three real recordings: correct a name, see the chip, accept, re-transcribe another recording and confirm the spelling (needs hardware: GPU and the downloaded model)

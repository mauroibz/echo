## 1. Data

- [x] 1.1 Item `uid`, `state`, `tracker`, `failure`; the file's `ready_at`; stable uids for items saved before them
- [x] 1.2 `mark_ready`, `unmark_ready`, `mark_sent`, `mark_failed`, `status`; sent items refuse edits and discards
- [x] 1.3 Merge keeps uids, and keeps ready, sent and failed items even when the model drops them
- [x] 1.4 Tests: the whole way, summarizing again in between, a meeting with nothing to send

## 2. Command line

- [x] 2.1 `actions --ready`, `item ID ITEM --sent/--failed`, `meetings --unprocessed`, the JSON's new keys; tests

## 3. Window

- [x] 3.1 The bar above the items: Ready to send… with the list to confirm, Back to review, Mark processed, failures, processed
- [x] 3.2 Rows: Ready chip, ✓ Sent · REF as a link without edit or discard, the failure line
- [x] 3.3 The open view follows outside writes; the Briefing card shows ✓ Processed and the counts
- [x] 3.4 Test in the window; screenshots in light and dark with an invented reference

## 4. Documents

- [x] 4.1 Guide, agent skill (sending for any tracker), Studio roadmap

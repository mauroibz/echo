## Decisions

- **Echo hands over and keeps what comes back; it never calls a tracker.** Routing an item to a
  project, mapping people to tracker members and finding duplicates are each team's own, and are
  usually already done by an agent. A connector inside Echo would duplicate that and tie Echo to
  one tracker. The command line is the contract instead: `actions --ready` out, and `item --sent`
  or `--failed` back in.
- **The user approves the meeting, not each item.** Marking the meeting ready approves every item
  not discarded, since discarding already says "not this one". The confirmation lists the items
  first, so the user sees what is approved. Anything that sends them should not ask again.
- **Sent items are frozen.** Once sent, the tracker holds the item. Echo keeps the reference and
  link, refuses edits and discards, and summarizing again keeps the item as it was. There is no
  sync back from the tracker.
- **Stable uids.** Indexes change when a summary is made again, so items get a 10-character uid.
  It is kept by merge for an item the model gives again. An item saved before uids gets one made
  from its origin, key and how many times that key came before, so it is the same on every read
  without writing on read; the next save stores it.
- **Processed** means `ready_at` is set and every item not discarded is sent. Adding an item
  afterwards makes the meeting unprocessed again, which is true: something new is unsent.
- **The open view follows outside writes** by checking `actions.json`'s modification time every
  2 seconds while it is shown and nothing is being edited. A file watcher would do the same with
  more moving parts, and atomic writes replace the file, which a watcher has to re-add.
- **`item`, not `mark`:** `echo-app mark` already adds a marker to a recording.

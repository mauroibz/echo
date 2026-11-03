## Context

`add-studio-tracker-handoff` let the user approve a whole meeting at once: every item not
discarded became `ready`. In use, most items are notes of what was said rather than tickets, so
the user had to discard items they wanted to keep just to keep them out of the tracker. The
items' column beside the summary was also too narrow once the window was not maximized.

## Decisions

- **Per-item switch, the state as it was.** The switch maps onto the states the sender already
  reads: on = `ready`, off = `proposed`. `echo-app actions --ready` and `echo-app item` do not
  change, so a sender written for 1.5.0 keeps working. A failed item shows its switch off with
  why; switching it on clears the failure and makes it ready.
- **Reviewed stays explicit.** With opt-in, "every item sent" no longer says the user is through
  with a meeting: a meeting with nothing switched on would be processed before the user looked at
  it. "Done with this meeting" sets `ready_at` (the key is kept; `data.py` only ever adds keys) and processed
  is reviewed with no item ready or failed.
- **Done is the user's mark, nothing more.** It is a user field (kept by `merge` like edits), a
  sent item takes it too since it changes nothing the tracker has, and version 1 files' `done` is
  read again. A done item folds to its struck-through title. This reverses `change-studio-action-edits`'s
  "no done flag" at the user's request; its reasons against late dates and a Pending screen still
  hold, so neither returns.
- **A view, not a screen.** The items belong to one meeting, next to its audio and summary, so
  they get a third tab in Echo's view switch rather than a rail page. The person page keeps its
  list, with the same checkbox and switch.
- **Record at the head of the rail.** It is an action, not a place, so it sits above the pages
  with space below. It wears the waveform (what the user associates with recording) and the
  Briefing gets a house. The Briefing's hero already became a recording screen once one started;
  a Record now there was tried and dropped once the rail's Record proved enough: one way to start.

## Decisions made while implementing

- Scrolling chugged: the lists sat on transparent backgrounds, so Qt repainted every visible card
  over the card behind on each step. Measured offscreen by counting paint events: 20 items, 33
  widget paints per step (1.8 ms) became 3.9 (0.3 ms); the Briefing with 12 cards, 65 became 6.
  The scroll contents are `widgets.Opaque`, which paints its theme color and sets
  `WA_OpaquePaintEvent`. A style-sheet background is not counted as opaque, and autofill is reset
  when the style sheet is polished at show time; the flag alone over a style-sheet background
  painted garbage.
- "Mark reviewed" read as unclear; it is "Done with this meeting" / "Not done yet", with the
  tooltip saying what follows (✓ Processed once what was switched on is sent).

- The Toggle widget takes a theme role: coral still means "will be recorded", accent means "goes
  to the tracker".
- The tab reads "Action items  N" with N the items not done and not discarded, and plain
  "Action items" when none are left.
- On a minutes card, done items carry ✓ and are dimmed; sent ones show the tracker's reference
  (the ✓ that marked them sent would now read as done).
- The hero's Record this meeting shows only while the next meeting is under way and not recorded,
  and names the recording after it.

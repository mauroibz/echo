## Why

Using Studio for a few days showed two things in the way:

- Recording started from Recordings, the list of past meetings. The rail's Record sat at the
  bottom as a small mic and went unnoticed, while the Briefing's icon was the waveform, the
  symbol Echo's Record wears. Starting a recording should not mean going to the past ones.
- Action items shared a column with the summary. In a narrow window the sidebar, the summary and
  the items all took space and the items were hard to work on. Working on them means checking
  them off, correcting them, and choosing which go to the tracker. Approving a whole meeting
  sent every item kept, but most items are not meant for a tracker: sending has to be opt-in.

## What Changes

- **Record everywhere.** Record heads the rail, above the pages, with the waveform icon and the
  elapsed time under it while recording; it starts and stops from any page. The Briefing's hero
  keeps Record this meeting while a meeting is under way and not recorded, and nothing else to
  record with: the rail's Record is the one way. The Briefing's icon is a house.
- **An Action items view.** Beside Transcript and Minutes, the selected recording's items get a
  view of their own, the width of the content. The tab shows how many are left to do. Minutes
  shows the summary alone. A minutes card's items on the Briefing open that view.
- **Done.** Each item has a checkbox: the user's check mark, kept when summarizing again and
  given in the command line's JSON (`done`) and text (`[x]`). No late dates, no reminders.
- **BREAKING** (released in 1.5.0): **sending is opt-in per item.** Each item has a To tracker
  switch, off by default; on makes it `ready`, off makes it `proposed`. Ready to send…, its
  confirmation and Back to review are gone. "Done with this meeting" (and "Not done yet") says
  nothing else from the meeting goes to the tracker, kept in `ready_at` as before. A meeting is processed when reviewed with no item
  ready or failed. Meetings marked ready under 1.5.0 keep their ready items, so nothing on its
  way changes.

- **No instructions on screen.** The view has no paragraph explaining itself; each control's
  tooltip says what it does.
- **Scrolling.** The Action items list, the Briefing and People paint an opaque background, so a
  scroll moves what is painted instead of repainting every card (it chugged on the user's screen).

## Capabilities

### Modified Capabilities

- `studio-actions` (from `add-studio-actions`, `change-studio-action-edits`,
  `refine-studio-after-first-use` and `add-studio-tracker-handoff`, not yet archived)
- `studio-home` (from `add-studio-home` and `refine-studio-after-first-use`, not yet archived)

## Impact

- Code: `src/echo_studio/actions.py`, `actions_ui.py`, `ui.py`, `home.py`, `window.py`,
  `widgets.py`, `data.py`, `cli.py`, `__init__.py`. Echo gains the `house` icon (Lucide).
- Files: `actions.json` items gain `done`; `ready_at` now means "reviewed".
- Command line: `done` in the item JSON and in `status`; help reworded. No command removed.
- `agents/echo/SKILL.md`, `docs/guide.md`, `docs/studio-roadmap.md`, `CHANGELOG.md`.
- No new dependency.

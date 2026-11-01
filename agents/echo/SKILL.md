---
name: echo
description: Read meeting minutes and action items from Echo, the meeting recorder on this machine. Use when asked what was said or agreed in a meeting, to list today's meetings, or to load a meeting's action items into a task tracker (Plane, Trello, Jira). Echo only reads here; loading items into the tracker is the caller's job.
---

# Reading Echo's meetings

Echo records meetings, transcribes them locally and, with Echo Studio, writes minutes: a summary
and action items the user polished (edited, given context, discarded). Everything below reads
what Echo saved and sends nothing anywhere. JSON keys are only ever added, never renamed.

## Commands

```sh
echo-app meetings --since today --json      # recordings with minutes, newest first
echo-app meetings --starred --json          # the meetings the user starred
echo-app minutes ID --json                  # one meeting: summary and action items
echo-app actions --since 2026-10-01 --json  # action items across meetings
echo-app actions --owner "Sofía Paz" --json # one person's items
echo-app export ID --format md              # the full transcript, with speakers
echo-app info ID --json                     # the recording itself
```

`--since` and `--until` take `YYYY-MM-DD`, `today` or `yesterday`.

## What an action item holds

```json
{"index": 0, "text": "Plan de pruebas del onboarding",
 "description": "Cubrir el alta con y sin tarjeta; Sofía lo quiere antes de la demo del jueves.",
 "owner": "Sofía Paz", "owner_email": "sofia@acme.example",
 "due": "2026-11-04", "at": 760.0, "at_stamp": "12:40",
 "context": "a line the user added for whoever picks it up",
 "note": "the user's own note",
 "edited": true, "added_by_user": false,
 "quote": "Sofía Paz: ¿Te encargás del plan de pruebas? ...",
 "recording": "20261031-110000-ab12", "title": "Product sync", "created": "2026-10-31T11:00:00-03:00"}
```

- `text` is the item's title as the user left it; prefer it over anything in the summary.
- `description` says what exactly and why, from what was said: the tracker item's body.
- `context` is the user's addition for whoever picks it up: carry it into the description too.
- `note` is the user's private note: do not put it in the tracker.
- `quote` is what was said around `at`; include it so the item can be checked.
- Discarded items are left out unless `--discarded` is given: the user threw them out.
- Echo does not know whether an item got done. Do not report items as late or pending from
  Echo's data.
- Meeting dicts may carry more keys as Echo grows (the calendar event, attendees' emails).

## Loading items into a tracker

Read the items with `echo-app minutes ID --json` (or `actions --since …`), map `owner` to the
tracker's member, and put `description`, `context`, `quote` and the meeting's title and date in the
description. To avoid loading an item twice, keep `(recording, index)` in the tracker item: an
item's index does not change when the user edits it, and items the user adds are appended.

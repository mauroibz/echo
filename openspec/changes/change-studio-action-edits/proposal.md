# Editable action items

## Why

Action items are what the user takes from a meeting to the team's tracker. The model gets most of
them right, but one needs rewording, another is not an action, a third lacks the context whoever
picks it up will need. Fixing that in Echo, next to the minutes and the audio, is quicker than
in the tracker. Tracking whether items got done is the tracker's job: in Echo the done flags
were upkeep, and the "late" dates and the Pending screen turned missing upkeep into noise.

## What Changes

- An item can be edited (text, owner, due date), given a line of context, discarded and
  restored, and added by hand. Summarizing again keeps the user's edits, context and discards
  for items that still match, and keeps the items the user added.
- **BREAKING (unreleased):** no done flag, no "late" dates, no Pending screen. Items are
  informative: a due date reads "by Nov 4". A person's profile lists the items assigned to them,
  without checkboxes.
- The follow-up draft leaves out discarded items.

## Capabilities

### Modified Capabilities

- `studio-actions` (from `add-studio-actions`, not yet archived)

## Impact

`src/echo_studio/actions.py`, `actions_ui.py`, `ui.py`, `followup.py`, `__init__.py`;
`tests/test_studio.py`; `docs/guide.md`, `docs/studio-roadmap.md`.

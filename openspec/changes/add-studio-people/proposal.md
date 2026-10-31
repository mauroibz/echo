# People by email, with their meetings

## Why

The user wants each person to carry what Echo knows about them: their meetings, their part in
each, the action items assigned to them, keyed by an email so the calendar's attendees and the
team's tracker can be matched to them.

## What Changes

- After each summary, one short request gives each named participant's part, kept in `parts.json`.
- Studio's People page: everyone, filtered by name or email; a person's page with their email,
  counts, meetings (excerpt and part), action items assigned to them (informative), notes, and a
  link to Echo's People window for aliases, tags and voice. A meeting counts as theirs when they
  speak in it, a speaker has their name, or its event invited their email.
- Echo base: the email on a profile (`add-background-and-email`).

## Capabilities

### New Capabilities

- `studio-people`

## Impact

`src/echo_studio/parts.py`, `people_ui.py` (new); `summary.py`; tests; guide.

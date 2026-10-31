# The calendar

## Why

Most of what the user records is a meeting in their calendar. The calendar already knows its
title, who was invited (with their emails) and what it is about; Studio should use that instead
of asking, and show the next meeting without being a copy of the calendar.

## What Changes

- Settings → Calendar: one or more private ICS addresses (Google Calendar, Outlook/Teams), kept
  in the keyring; Test reads them. `echo-app calendar` lists the next meetings.
- Studio reads them every 10 minutes and keeps the last copy in the cache.
- A recording made during an event gets it as `event.json`: an unnamed recording takes the
  event's title, transcription gets the attendees' names as context, the summary gets the
  event's title, invitees and invitation text, and the people named in it learn their email from
  the attendee with their name.
- `minutes --json` and `meetings --json` gain `event` and `attendees`; items gain `owner_email`.

## Capabilities

### New Capabilities

- `studio-calendar`

## Impact

`src/echo_studio/ics.py`, `calendar.py`, `calendar_ui.py`, `meetings.py` (new); `summary.py`,
`data.py`, `cli.py`, `keychain.py`, `__init__.py`; `tests/test_studio_calendar.py`; guide.

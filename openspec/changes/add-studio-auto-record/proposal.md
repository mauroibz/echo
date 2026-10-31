# Recording the meetings in the calendar

## Why

The user forgets to press Record when a call starts. The calendar says when it starts and that it
is a call.

## What Changes

- When a calendar event with a video link starts and Echo is running, Studio starts a recording
  titled after it (if nothing is being recorded), and stops it 10 minutes after the event ends
  unless the user stopped it. A meeting is started once; Skip on the home leaves it alone.
- Settings → Calendar: "Record the meetings that have a video link when they start" (on), with a
  note pointing to "Keep Echo running in the tray" when that is off.

## Capabilities

### New Capabilities

- `studio-auto-record`

## Impact

`src/echo_studio/meetings.py`, `calendar_ui.py`, `config.py`; uses Echo's `start_recording`
and background mode (`add-background-and-email`); tests; guide.

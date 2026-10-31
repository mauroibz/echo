# Studio's home and window

## Why

With Studio, the center of Echo is the meeting and its minutes, not the recorder. The user asked
for a window that feels like that, with Lagoon's boldest styling, and that shows what the
calendar and the recordings say without becoming a management tool.

## What Changes

- `window_class` gives Studio's window: Echo's window inside a rail with Home, Recordings (Echo's
  window unchanged), People, Ask and Record. The rail shows once a server or a calendar is set.
- Home: a deep hero band ending in waves with the next meeting (time in large type, title,
  invitation, attendees as avatars, Join the call, records by itself / Skip / Record now), or the
  recording in progress (timer, notes that lead the minutes, invited people, Stop); below, the
  minutes as a timeline. A minute opens its recording on the Minutes view.
- The Summary view is called Minutes. Ask is a rail page.

## Capabilities

### New Capabilities

- `studio-home`

## Impact

`src/echo_studio/window.py`, `home.py`, `widgets.py` (new); `__init__.py`, `ui.py`; tests; guide.

# Running in the background, recording for an extension, and a person's email

## Why

Echo Studio is going to record the meetings in the user's calendar. For that Echo has to be
running when a meeting starts (in the tray, started at login), an extension has to be able to
start and stop a recording, and a person needs an email to be matched to an event's attendees.

## What Changes

- Settings → General: "Keep Echo running in the tray, and start it when you log in". Closing the
  window then leaves Echo in the tray; an XDG autostart entry runs `echo-app gui --background`,
  which starts without the window.
- `MainWindow.start_recording(title)`, `stop_recording()`, `recording_id()`.
- A person's profile keeps an email (People shows and edits it; `people --json` has it);
  `people.by_email`.

## Capabilities

### Modified Capabilities

- `desktop-app`, `extensions`, `library-storage`, `command-line`

## Impact

`src/echo_app/autostart.py` (new), `settings.py`, `people.py`, `cli.py`, `ui/app.py`,
`ui/main_window.py`, `ui/dialogs.py`, `ui/people.py`; tests; `docs/guide.md`, `CHANGELOG.md`.

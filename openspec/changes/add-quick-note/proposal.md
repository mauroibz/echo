# Proposal

## Why

The fastest way to capture a thought is to say it. Starting Echo, pressing Record and later
copying the text is three steps too many for a two-sentence note.

## What Changes

- A system-wide shortcut starts and stops a recording while Echo runs in the tray. On KDE
  and GNOME this registers through the desktop's global shortcuts portal; where no portal
  exists the user binds `echo-app record --toggle` to a key themselves, which the settings page
  explains.
- "Quick note": a second shortcut records until pressed again, then, when the transcript is
  ready, copies the text to the clipboard and shows a notification. The note is kept in the
  library like any recording, tagged `nota`.
- Auto title: a recording the user has not renamed takes its title from the first sentence of
  the transcript (up to 60 characters) instead of the timestamp; renaming turns this off for
  that recording.

## Capabilities

### Modified Capabilities
- `desktop-app`: global shortcuts, quick note, auto titles.

## Impact

`ui/app.py` (portal registration via D-Bus), `cli_rec.py` (`--toggle`), `ui/main_window.py`
(notification and clipboard on transcript ready), `library.py` (`title_auto` flag).

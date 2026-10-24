# Tasks

- [x] 1.1 `echo-app record --toggle` and `--quick-note` (tag and clipboard flag in `meta.json`)
- [ ] 1.2 Global shortcuts through the XDG GlobalShortcuts portal when available; settings page explaining manual binding otherwise; verify on KDE Wayland and GNOME (needs hardware: a KDE or GNOME desktop session)
- [x] 1.3 Clipboard and notification on transcript ready for quick notes; auto title with `title_auto`; tests

## Blocked

- **1.2** is implemented (portal client in `ui/shortcuts.py`, Settings explanation when there is
  no portal). Verified here without a person: on this KDE Plasma session the portal's
  GlobalShortcuts interface (version 2) answers, a session is created and `ListShortcuts` works.
  Binding shows the desktop's confirmation dialog, so it needs someone at the computer: start
  Echo on KDE Wayland, accept Ctrl+Alt+R and Ctrl+Alt+N in the dialog, then press them from
  another application (recording starts and stops; a quick note's text lands on the clipboard
  with a notification). Repeat on GNOME 46 or newer.

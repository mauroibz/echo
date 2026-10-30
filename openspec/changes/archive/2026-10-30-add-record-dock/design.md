# Design

## Decisions

- **A separate top-level widget, driven by the recorder panel.** `RecordDock` is a frameless,
  translucent `Qt.Tool` window with `WindowStaysOnTopHint`. It owns no recording logic: Record,
  Pause, Stop and Marker call `RecorderPanel`, and it reads the session's status the way the panel
  does, on its own 200 ms timer while it is shown. Closing it (Done, or back to the window) never
  touches the recording.
- **Deep in both appearances.** The canvas showed a light variant; the dock keeps the deep
  sidebar gradient in both, so it reads as Echo over any window and over any theme, and there is
  one look to maintain.
- **Moving.** A press anywhere that is not a button starts `startSystemMove()`, which works on
  Wayland, where a window cannot place itself. The position is saved in the UI state and
  restored where the platform allows it (X11; on Wayland the compositor places the dock).
- **Always on top on Wayland.** Qt passes `WindowStaysOnTopHint` on X11 and on KDE Plasma
  through its integration; GNOME on Wayland does not let an application keep a window above
  others. There the dock is a small normal window: Ctrl+Shift+D, the tray and Ctrl+Alt+R still
  reach it. The guide says so.
- **Seen on KDE Plasma, Wayland (task 1.3).** The dock does not stay above other windows
  either: KWin ignores the hint from a native Wayland client. Everything else worked. Left as
  it is: the user does not want the dock above everything all the time, and KWin can keep it
  above on request (Alt+F3 → More Actions → Keep Above Others, or a window rule for the title
  "Echo recording"). Ways to force it were weighed and not taken: running the dock under
  XWayland would move the whole window process off Wayland, a KWin script loaded over D-Bus
  reaches into the user's compositor, and layer-shell needs a library PySide6 does not ship.
- **Markers from the dock** are taken without the note field (it lives in the hidden window),
  as from the tray; the dock counts the markers of the current recording.
- **Minimal state** after 5 s without the pointer while recording, never at rest or after Stop,
  and never while a problem is shown.
- **Saved state** lasts 10 s, or until Done or Open; Open shows the window with the new
  recording selected.
